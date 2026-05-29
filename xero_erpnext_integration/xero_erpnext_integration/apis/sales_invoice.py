import re
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import cint, flt

from .base import get_xero_client
from .item import ensure_xero_items_for_lines, resolve_line_item_code

# ---------------------------------------------------------------------------
# Line item helpers (shared by Sales Invoice and Credit Note line construction)
# ---------------------------------------------------------------------------


def _account_xero_tax_type(account_head):
	"""Return the Xero TaxType stored on an ERPNext Account, if any."""
	if not account_head:
		return None
	return frappe.db.get_value("Account", account_head, "custom_xero_tax_type")


def _erpnext_account_to_xero_code(account_name: str | None) -> str | None:
	"""Map an ERPNext Account name to a Xero account code (number or custom field)."""
	if not account_name:
		return None
	if frappe.db.has_column("Account", "account_number"):
		code = frappe.db.get_value("Account", account_name, "account_number")
		if code:
			return str(code).strip()
	if frappe.db.has_column("Account", "custom_account_code"):
		code = frappe.db.get_value("Account", account_name, "custom_account_code")
		if code:
			return str(code).strip()
	return None


def _resolve_xero_account_code(item, invoice) -> str | None:
	"""Resolve the Xero AccountCode for an invoice line.

	Priority:
	1. Line-level custom_account_code (if present on the item row)
	2. Item income account (row or Item Default)
	3. Xero Settings `default_account_code`
	"""
	custom = (
		item.get("custom_account_code")
		if hasattr(item, "get")
		else getattr(item, "custom_account_code", None)
	)
	if custom:
		return str(custom).strip()

	income_account = (
		item.get("income_account") if hasattr(item, "get") else getattr(item, "income_account", None)
	)
	code = _erpnext_account_to_xero_code(income_account)
	if code:
		return code

	item_code = item.get("item_code") if hasattr(item, "get") else getattr(item, "item_code", None)
	if item_code:
		default_income = frappe.db.get_value(
			"Item Default",
			{"parent": item_code, "parenttype": "Item", "company": invoice.company},
			"income_account",
		)
		code = _erpnext_account_to_xero_code(default_income)
		if code:
			return code

	settings_code = frappe.db.get_single_value("Xero Settings", "default_account_code")
	if settings_code:
		return str(settings_code).strip()

	return None


def get_line_tax_type(item, invoice):
	"""Pick the Xero TaxType for a single Sales Invoice / Sales Return line.

	Resolution order:
	1. Per-line `item_tax_rate` (JSON of {account_head: rate}) - look up the first
	   account_head whose ERPNext Account has `custom_xero_tax_type` set.
	2. Invoice-level `taxes` table - first row whose `account_head` has
	   `custom_xero_tax_type` set.
	3. Fallback to "NONE" (no tax) so the request remains valid.
	"""
	raw = item.get("item_tax_rate") if hasattr(item, "get") else getattr(item, "item_tax_rate", None)
	if raw:
		try:
			tax_map = frappe.parse_json(raw) or {}
		except Exception:
			tax_map = {}
		for account_head in tax_map.keys():
			tt = _account_xero_tax_type(account_head)
			if tt:
				return tt

	for tax in getattr(invoice, "taxes", None) or []:
		tt = _account_xero_tax_type(tax.get("account_head") if hasattr(tax, "get") else tax.account_head)
		if tt:
			return tt

	default_tt = frappe.db.get_single_value("Xero Settings", "default_tax_type")
	if default_tt:
		return default_tt

	return "NONE"


def get_line_amount_types(invoice):
	"""Map ERPNext tax setup to Xero's LineAmountTypes.

	- No taxes on the invoice -> "NoTax"
	- Any tax row with `included_in_print_rate` -> "Inclusive"
	- Otherwise -> "Exclusive"
	"""
	taxes = getattr(invoice, "taxes", None) or []
	if not taxes:
		return "NoTax"

	for tax in taxes:
		incl = (
			tax.get("included_in_print_rate")
			if hasattr(tax, "get")
			else getattr(tax, "included_in_print_rate", 0)
		)
		if cint(incl):
			return "Inclusive"
	return "Exclusive"


def build_xero_line_item(item, invoice, line_amount_types="Exclusive", item_code_map=None):
	"""Build a single Xero LineItem payload from an ERPNext invoice line.

	ItemCode is only set when the item exists in Xero (see `ensure_xero_items_for_lines`).
	Includes a resolved TaxType so Xero can calculate tax on the line.
	"""
	account_code = _resolve_xero_account_code(item, invoice)
	if not account_code:
		frappe.throw(
			_(
				"Could not resolve a Xero Account Code for item {0}. "
				"Set income account on the line/item, or configure Default Account Code in Xero Settings."
			).format(item.get("item_code") or item.item_name or item.name)
		)

	line_item = {
		"Description": item.description or item.item_name,
		"Quantity": str(flt(item.qty)),
		"UnitAmount": str(flt(item.rate)),
		"AccountCode": account_code,
	}

	xero_item_code = resolve_line_item_code(item, item_code_map)
	if xero_item_code:
		line_item["ItemCode"] = xero_item_code

	if line_amount_types == "NoTax":
		line_item["TaxType"] = "NONE"
	else:
		line_item["TaxType"] = get_line_tax_type(item, invoice) or "NONE"

	if item.get("discount_percentage"):
		line_item["DiscountRate"] = str(item.discount_percentage)

	return line_item


@frappe.whitelist()
def sync_selected_invoices(invoices: str):
	"""
	Bulk sync selected Sales Invoices to Xero.

	Only sync invoices that:
	- are submitted (`docstatus == 1`)
	- have `custom_do_not_sync_to_xero` unchecked
	- have no `custom_xero_invoice_number` yet
	"""
	invoice_names = frappe.parse_json(invoices) or []
	if not isinstance(invoice_names, list):
		frappe.throw(_("Invalid invoices payload"))

	invoice_names = [name for name in invoice_names if name]
	if not invoice_names:
		return {"created": [], "skipped": [], "failed": []}

	rows = frappe.get_all(
		"Sales Invoice",
		filters={"name": ["in", invoice_names]},
		fields=[
			"name",
			"docstatus",
			"custom_do_not_sync_to_xero",
			"is_return",
			"custom_xero_invoice_number",
		],
		limit=len(invoice_names),
	)
	by_name = {row.name: row for row in rows}

	results = {"created": [], "skipped": [], "failed": []}
	invoice_updates: dict[str, dict] = {}

	for name in invoice_names:
		try:
			si = by_name.get(name)
			if not si:
				results["failed"].append({"name": name, "error": _("Sales Invoice not found")})
				continue

			# Only sync submitted invoices
			if si.docstatus != 1:
				results["skipped"].append({"name": si.name, "reason": "Not submitted"})
				continue

			# Respect per-invoice opt-out
			if getattr(si, "custom_do_not_sync_to_xero", 0):
				results["skipped"].append({"name": si.name, "reason": "Xero sync disabled"})
				continue

			# Returns must be synced as Credit Notes (not invoices)
			if getattr(si, "is_return", 0):
				results["skipped"].append({"name": si.name, "reason": "Return invoice: sync as Credit Note"})
				continue

			# Only invoices not yet synced
			if getattr(si, "custom_xero_invoice_number", None):
				results["skipped"].append({"name": si.name, "reason": "Already synced"})
				continue

			res = create_invoice(si.name, update=False)

			if not res or res.get("status") != "success":
				results["failed"].append(
					{"name": si.name, "error": (res or {}).get("message") or "Unknown error"}
				)
				continue

			xero_invoice = res.get("data") or {}
			xero_id = xero_invoice.get("InvoiceID")
			if xero_id:
				invoice_updates[si.name] = {"custom_xero_invoice_number": xero_id}

			results["created"].append({"name": si.name, "xero_invoice_id": xero_id})

		except Exception as e:
			results["failed"].append({"name": name, "error": str(e)})

	if invoice_updates:
		frappe.db.bulk_update("Sales Invoice", invoice_updates)

	return results


@frappe.whitelist()
def sync_invoice_payments():
	"""Sync payment status from Xero and create payment entries for paid invoices"""
	try:
		# Migration guide: operator-value pairs in dict filters → 3-element list-of-lists
		# OLD: filters={"custom_xero_invoice_number": ["is", "set"], "status": ["in", [...]]}
		# NEW: filters=[["field", "operator", "value"], ...]
		unpaid_invoices = frappe.get_all(  # nosemgrep — scheduler must process all pending invoices; a limit would silently skip records
			"Sales Invoice",
			filters=[
				["custom_xero_invoice_number", "is", "set"],
				["status", "in", ["Draft", "Unpaid", "Overdue", "Partly Paid"]],
				["workflow_state", "in", ["Synced to Xero", "Submitted"]],
			],
			fields=[
				"name",
				"customer",
				"grand_total",
				"outstanding_amount",
				"custom_xero_invoice_number",
				"company",
			],
			ignore_permissions=True,
		)

		if not unpaid_invoices:
			return {"status": "success", "message": "No unpaid invoices found with Xero references"}

		invoice_ids = [invoice.custom_xero_invoice_number for invoice in unpaid_invoices]
		invoice_ids_str = ",".join(invoice_ids)

		client = get_xero_client()
		response = client.make_request("GET", f"/invoices?IDs={invoice_ids_str}")

		xero_invoices = response.get("Invoices", [])
		processed_invoices = []

		for xero_invoice in xero_invoices:
			invoice_id = xero_invoice.get("InvoiceID")
			status = xero_invoice.get("Status")
			amount_paid = flt(xero_invoice.get("AmountPaid", 0))

			erpnext_invoice = None
			for inv in unpaid_invoices:
				if inv.custom_xero_invoice_number == invoice_id:
					erpnext_invoice = inv
					break

			if not erpnext_invoice:
				continue

			if status in ["PAID", "AUTHORISED"] and amount_paid > 0:
				# A9 fix: check payment_result before appending to processed list
				payment_result = create_payment_entry_from_xero(erpnext_invoice, xero_invoice, amount_paid)
				if payment_result and payment_result.get("status") == "success":
					processed_invoices.append(
						{
							"invoice": erpnext_invoice.name,
							"amount_paid": amount_paid,
						}
					)

		return {
			"status": "success",
			"message": f"Processed {len(processed_invoices)} invoices",
			"data": processed_invoices,
		}

	except Exception as e:
		frappe.log_error(title="Xero Payment Sync", message=f"Error syncing invoice payments: {e!s}")
		return {"status": "error", "message": str(e)}


def create_payment_entry_from_xero(erpnext_invoice, xero_invoice, amount_paid):
	"""Create payment entry in ERPNext based on Xero payment data"""
	try:
		invoice_id = xero_invoice.get("InvoiceID")
		client = get_xero_client()

		payments_response = client.make_request(
			"GET", f"/Payments?where=Invoice.InvoiceID%3DGuid%28%22{invoice_id}%22%29"
		)
		payments = payments_response.get("Payments", [])

		if not payments:
			return {"status": "error", "message": "No payments found in Xero"}

		sales_invoice = frappe.get_doc("Sales Invoice", erpnext_invoice.name)
		try:
			# B6 fix: use doc.get() instead of hasattr()
			if sales_invoice.get("workflow_state") == "Synced to Xero":
				sales_invoice.workflow_state = "Submitted"
				# B4 fix: ignore_permissions — called from scheduler context
				sales_invoice.save(ignore_permissions=True)
				sales_invoice.submit()
				# B5 fix: no frappe.db.commit() — framework manages the transaction
		except Exception as workflow_error:
			frappe.log_error(
				title="Workflow State Change",
				message=f"Error changing workflow state for {sales_invoice.name}: {workflow_error!s}",
			)

		# C4 fix: query Payment Entry Reference child table for existing payments.
		# Migration guide: dict filters with operators → 3-element list-of-lists.
		# Step 1: get parent PE names from the child table
		existing_payment_refs = frappe.get_all(  # nosemgrep — scoped to one invoice; result count is naturally bounded by payment history
			"Payment Entry Reference",
			filters=[
				["reference_doctype", "=", "Sales Invoice"],
				["reference_name", "=", sales_invoice.name],
				["parenttype", "=", "Payment Entry"],
			],
			fields=["parent", "allocated_amount"],
			ignore_permissions=True,
		)

		existing_payment_names = [ref.parent for ref in existing_payment_refs]
		total_existing_payments = flt(0)
		if existing_payment_names:
			# Step 2: filter only submitted entries
			# Migration guide: ["in", [...]] dict operator → list-of-lists
			submitted = frappe.get_all(  # nosemgrep — filtered by existing_payment_names list which is already bounded above
				"Payment Entry",
				filters=[
					["name", "in", existing_payment_names],
					["docstatus", "=", 1],
				],
				fields=["name", "paid_amount"],
				ignore_permissions=True,
			)
			total_existing_payments = sum(flt(pe.paid_amount) for pe in submitted)

		remaining_amount = flt(amount_paid) - total_existing_payments

		if remaining_amount <= 0:
			return {"status": "info", "message": "Payment already recorded"}

		latest_payment = max(payments, key=lambda x: x.get("UpdatedDateUTC", ""))
		payment_date = latest_payment.get("Date", "")

		if payment_date:
			date_match = re.search(r"/Date\((\d+)", payment_date)
			if date_match:
				timestamp = int(date_match.group(1)) / 1000
				payment_date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
			else:
				payment_date = frappe.utils.today()
		else:
			payment_date = frappe.utils.today()

		payment_entry = frappe.new_doc("Payment Entry")
		payment_entry.payment_type = "Receive"
		payment_entry.party_type = "Customer"
		payment_entry.party = sales_invoice.customer
		payment_entry.mode_of_payment = "Cash"
		payment_entry.company = sales_invoice.company
		payment_entry.posting_date = payment_date
		payment_entry.paid_amount = remaining_amount
		payment_entry.received_amount = remaining_amount
		payment_entry.reference_no = latest_payment.get("PaymentID", f"Xero-{invoice_id[:8]}")
		payment_entry.reference_date = payment_date
		payment_entry.remarks = f"Payment synced from Xero for Invoice {sales_invoice.name}"

		company_doc = frappe.get_doc("Company", sales_invoice.company)

		# B6 fix: use doc.get() instead of hasattr()
		paid_to_account = None
		if company_doc.get("default_cash_account"):
			paid_to_account = company_doc.default_cash_account
		elif company_doc.get("default_bank_account"):
			paid_to_account = company_doc.default_bank_account
		else:
			# Migration guide: ["in", [...]] dict operator → list-of-lists
			cash_accounts = frappe.get_all(
				"Account",
				filters=[
					["company", "=", sales_invoice.company],
					["account_type", "in", ["Cash", "Bank"]],
					["is_group", "=", 0],
				],
				fields=["name"],
				limit=1,
				ignore_permissions=True,
			)
			if cash_accounts:
				paid_to_account = cash_accounts[0].name

		if not paid_to_account:
			return {
				"status": "error",
				"message": f"No cash/bank account found for company {sales_invoice.company}",
			}

		payment_entry.paid_to = paid_to_account

		customer_doc = frappe.get_doc("Customer", sales_invoice.customer)
		# B6 fix: use doc.get() instead of hasattr()
		if customer_doc.get("accounts"):
			for acc in customer_doc.accounts:
				if acc.company == sales_invoice.company:
					payment_entry.paid_from = acc.account
					break

		if not payment_entry.paid_from:
			# Migration guide: simple equality filters — dict form is fine, using list for consistency
			receivable_accounts = frappe.get_all(
				"Account",
				filters=[
					["company", "=", sales_invoice.company],
					["account_type", "=", "Receivable"],
					["is_group", "=", 0],
				],
				fields=["name"],
				limit=1,
				ignore_permissions=True,
			)
			if receivable_accounts:
				payment_entry.paid_from = receivable_accounts[0].name
			else:
				return {
					"status": "error",
					"message": f"No receivable account found for company {sales_invoice.company}",
				}

		payment_entry.append(
			"references",
			{
				"reference_doctype": "Sales Invoice",
				"reference_name": sales_invoice.name,
				"allocated_amount": remaining_amount,
			},
		)

		# B4 fix: ignore_permissions — called from scheduler context
		payment_entry.insert(ignore_permissions=True)
		payment_entry.submit()

		return {
			"status": "success",
			"message": f"Payment Entry {payment_entry.name} created",
			"payment_entry": payment_entry.name,
		}

	except Exception as e:
		frappe.log_error(title="Xero Payment Entry Creation", message=f"Error creating payment entry: {e!s}")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def create_invoice(doc: str, method: str | None = None, update_invoice: bool = False) -> dict:
	"""Create invoice in Xero"""
	try:
		client = get_xero_client()

		if isinstance(doc, str):
			invoice = frappe.get_doc("Sales Invoice", doc)
		# B6 fix: use doc.get() instead of hasattr()
		elif doc.get("doctype") == "Sales Invoice":
			invoice = doc

		if getattr(invoice, "is_return", 0):
			frappe.throw(
				_(
					"This Sales Invoice is a return (negative quantities). "
					"Xero does not accept negative ACCREC invoices. "
					"Please sync it as a Credit Note instead."
				)
			)

		contact_id = get_customer_contact_id(invoice.customer)
		if not contact_id:
			frappe.throw(_("No Xero Contact ID found for customer: {0}").format(invoice.customer))

		# Build a tax-rate lookup keyed by item_code for per-item tax rates
		# Falls back to the invoice-level effective tax rate if no per-item breakdown
		invoice_tax_rate = flt(0)
		if invoice.taxes:
			for tax in invoice.taxes:
				if tax.charge_type == "On Net Total":
					invoice_tax_rate += flt(tax.rate)

		# Decide LineAmountTypes once for the whole document
		line_amount_types = get_line_amount_types(invoice)

		# Create any missing items in Xero so ItemCode on lines is valid
		item_code_map = ensure_xero_items_for_lines(invoice.items, client=client)

		# Prepare line items (with ItemCode + TaxType so Xero can compute tax)
		line_items = [
			build_xero_line_item(
				item, invoice, line_amount_types=line_amount_types, item_code_map=item_code_map
			)
			for item in invoice.items
		]

		if not invoice.posting_date:
			frappe.throw(_("Posting date is required for invoice {0}").format(invoice.name))
		if not invoice.due_date:
			frappe.throw(_("Due date is required for invoice {0}").format(invoice.name))

		invoice_data = {
			"Type": "ACCREC",
			"Contact": {"ContactID": contact_id},
			"InvoiceNumber": invoice.name,
			"DateString": invoice.posting_date.strftime("%Y-%m-%d") if invoice.posting_date else None,
			"DueDateString": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else None,
			"LineAmountTypes": line_amount_types,
			"LineItems": line_items,
			"Reference": invoice.name,
			"Status": "AUTHORISED",
		}

		if invoice.currency and invoice.currency != frappe.get_cached_value(
			"Company", invoice.company, "default_currency"
		):
			invoice_data["CurrencyCode"] = invoice.currency

		data = {"Invoices": [invoice_data]}
		try:
			if (
				invoice.custom_xero_invoice_number
				and invoice.workflow_state == "Synced to Xero"
				and update_invoice
			):
				response = client.make_request(
					"POST", f"/Invoices/{invoice.custom_xero_invoice_number}", data=data
				)
			else:
				response = client.make_request("POST", "/Invoices", data=data)
		except Exception as api_error:
			frappe.log_error(title="Xero API Call", message=f"Xero API call failed: {api_error!s}")
			frappe.throw(_("Failed to communicate with Xero API: {0}").format(str(api_error)))

		if response and "Invoices" in response:
			xero_invoice = response["Invoices"][0]
			return {
				"status": "success",
				"data": xero_invoice,
				"message": f"Invoice created in Xero with ID: {xero_invoice.get('InvoiceID')}",
			}

		return {"status": "error", "message": "Failed to create invoice in Xero"}

	except Exception as e:
		# C7 fix: log_error once — frappe.throw() logs internally too
		frappe.log_error(title="Xero Create Invoice", message=f"Failed to create invoice in Xero: {e!s}")
		frappe.throw(_("Failed to create invoice in Xero: {0}").format(str(e)))


@frappe.whitelist()
def fetch_xero_contacts(contact_person: str) -> list:
	"""Fetch contacts from Xero and filter by similar names to contact person"""
	try:
		client = get_xero_client()
		response = client.make_request("GET", "/Contacts")

		xero_contacts = response.get("Contacts", [])
		contact_doc = frappe.get_doc("Contact", contact_person)
		contact_name = contact_doc.name or ""

		similar_contacts = []
		for contact in xero_contacts:
			xero_name = contact.get("Name", "").lower()
			contact_name_lower = contact_name.lower()

			if (
				xero_name in contact_name_lower
				or contact_name_lower in xero_name
				or any(word in xero_name for word in contact_name_lower.split() if len(word) > 2)
			):
				similar_contacts.append(contact)

		return similar_contacts

	except Exception as e:
		frappe.log_error(title="Fetch Xero Contacts", message=f"Failed to fetch Xero contacts: {e!s}")
		return []


@frappe.whitelist()
def create_contact_and_map(contact_person: str, sales_invoice: str) -> dict:
	"""Create contact in Xero using ERPNext contact details and map it"""
	try:
		contact_doc = frappe.get_doc("Contact", contact_person)

		is_customer = False
		is_supplier = False

		# B6 fix: use doc.get() instead of hasattr()
		if contact_doc.get("links"):
			for link in contact_doc.links:
				if link.link_doctype == "Customer":
					is_customer = True
				if link.link_doctype == "Supplier":
					is_supplier = True

		client = get_xero_client()
		contact_data = {
			"Name": contact_doc.name,
			"FirstName": contact_doc.first_name or "",
			"LastName": contact_doc.last_name or "",
			"EmailAddress": contact_doc.email_id or "",
			"AccountNumber": contact_doc.custom_account_number or contact_doc.name,
			"IsCustomer": is_customer,
			"IsSupplier": is_supplier,
			"Addresses": [{"AddressType": "STREET", "AddressLine1": contact_doc.address or ""}],
			"Phones": [
				{"PhoneType": "DEFAULT", "PhoneNumber": contact_doc.phone or contact_doc.mobile_no or ""}
			],
		}

		data = {"Contacts": [contact_data]}
		response = client.make_request("POST", "/Contacts", data=data)

		if response and response.get("Contacts"):
			contact_id = response["Contacts"][0].get("ContactID")
			map_result = map_contact_to_xero(contact_id, contact_person, sales_invoice)
			if map_result:
				return {
					"status": "success",
					"contact_id": contact_id,
					"message": "Contact created and mapped successfully",
				}

		return {"status": "error", "message": "Failed to create contact in Xero"}

	except Exception as e:
		frappe.log_error(title="Create Contact and Map", message=f"Failed to create and map contact: {e!s}")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def map_contact_to_xero(contact_id: str, contact_person: str, sales_invoice: str) -> bool:
	"""Map contact to Xero by setting contact_id in Contact and Sales Invoice"""
	try:
		contact_doc = frappe.get_doc("Contact", contact_person)
		contact_doc.custom_contact_id = contact_id
		contact_doc.custom_send_to_xero = 1
		contact_doc.save(ignore_permissions=True)

		sales_invoice_doc = frappe.get_doc("Sales Invoice", sales_invoice)
		sales_invoice_doc.custom_contact_id = contact_id
		sales_invoice_doc.save(ignore_permissions=True)

		return True

	except Exception as e:
		frappe.log_error(title="Map Contact to Xero", message=f"Failed to map contact: {e!s}")
		return False


@frappe.whitelist()
def cancel_invoice_in_xero(xero_invoice_id: str) -> dict:
	"""Cancel/void an invoice in Xero"""
	try:
		client = get_xero_client()

		response = client.make_request("GET", f"/Invoices/{xero_invoice_id}")

		if not response or "Invoices" not in response:
			return {"status": "error", "message": "Invoice not found in Xero"}

		current_invoice = response["Invoices"][0]
		current_status = current_invoice.get("Status")

		if current_status in ["PAID", "VOIDED"]:
			return {
				"status": "info",
				"message": f"Invoice cannot be cancelled as it is already {current_status}",
			}

		data = {"Invoices": [{"InvoiceID": xero_invoice_id, "Status": "VOIDED"}]}
		response = client.make_request("POST", "/Invoices", data=data)

		if response and "Invoices" in response:
			return {
				"status": "success",
				"message": f"Invoice {xero_invoice_id} cancelled successfully in Xero",
				"data": response["Invoices"][0],
			}

		return {"status": "error", "message": "Failed to cancel invoice in Xero"}

	except Exception as e:
		frappe.log_error(
			title="Xero Cancel Invoice",
			message=f"Failed to cancel invoice {xero_invoice_id} in Xero: {e!s}",
		)
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_customer_contact_id(customer: str) -> str | None:
	"""Get customer contact ID from Xero"""
	try:
		customer_doc = frappe.get_doc("Customer", customer)
		if customer_doc.get("custom_contact_id"):
			return customer_doc.get("custom_contact_id")

		dynamic_links = frappe.get_all(
			"Dynamic Link",
			filters=[
				["link_doctype", "=", "Customer"],
				["link_name", "=", customer],
				["parenttype", "=", "Contact"],
			],
			fields=["parent"],
			limit=1,
		)

		if dynamic_links:
			contact_name = dynamic_links[0].parent
			contact = frappe.get_doc("Contact", contact_name)
			return contact.get("custom_contact_id")

		return None
	except Exception as e:
		frappe.log_error(
			title="Get Customer Contact ID",
			message=f"Error getting contact id for customer {customer}: {e!s}",
		)
		frappe.throw(_("Error getting contact id for the selected customer"))
