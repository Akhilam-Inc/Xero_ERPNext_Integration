from datetime import datetime

import frappe
from frappe.utils import flt

from .base import get_xero_client


@frappe.whitelist()
def sync_invoice_payments():
	"""Sync payment status from Xero and create payment entries for paid invoices"""
	try:
		# Get unpaid invoices from ERPNext that have Xero invoice numbers
		unpaid_invoices = frappe.get_all(
			"Sales Invoice",
			filters={"custom_xero_invoice_number": ["is", "set"], "status": ["in", ["Unpaid", "Overdue"]]},
			fields=[
				"name",
				"customer",
				"grand_total",
				"outstanding_amount",
				"custom_xero_invoice_number",
				"company",
			],
		)

		if not unpaid_invoices:
			return {"status": "success", "message": "No unpaid invoices found with Xero references"}

		# Get Xero invoice IDs
		invoice_ids = [invoice.custom_xero_invoice_number for invoice in unpaid_invoices]
		invoice_ids_str = ",".join(invoice_ids)

		# Fetch invoice details from Xero
		client = get_xero_client()
		response = client.make_request("GET", f"/invoices?IDs={invoice_ids_str}")

		xero_invoices = response.get("Invoices", [])
		processed_invoices = []

		for xero_invoice in xero_invoices:
			invoice_id = xero_invoice.get("InvoiceID")
			status = xero_invoice.get("Status")
			amount_paid = flt(xero_invoice.get("AmountPaid", 0))

			# Find corresponding ERPNext invoice
			erpnext_invoice = None
			for inv in unpaid_invoices:
				if inv.custom_xero_invoice_number == invoice_id:
					erpnext_invoice = inv
					break

			if not erpnext_invoice:
				continue

			# Check if invoice is paid or partially paid in Xero
			if status in ["PAID", "AUTHORISED"] and amount_paid > 0:
				payment_result = create_payment_entry_from_xero(erpnext_invoice, xero_invoice, amount_paid)
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
		frappe.log_error("Xero Payment Sync", f"Error syncing invoice payments: {str(e)}")
		return {"status": "error", "message": str(e)}


def create_payment_entry_from_xero(erpnext_invoice, xero_invoice, amount_paid):
	"""Create payment entry in ERPNext based on Xero payment data"""
	try:
		# Get payment details from Xero
		invoice_id = xero_invoice.get("InvoiceID")
		client = get_xero_client()

		# Fetch payments for this specific invoice
		payments_response = client.make_request(
			"GET", f"/Payments?where=Invoice.InvoiceID%3DGuid%28%22{invoice_id}%22%29"
		)
		payments = payments_response.get("Payments", [])

		if not payments:
			return {"status": "error", "message": "No payments found in Xero"}

		# Get the Sales Invoice document
		sales_invoice = frappe.get_doc("Sales Invoice", erpnext_invoice.name)

		# Check if payment entry already exists
		existing_payments = frappe.get_all(
			"Payment Entry",
			filters={
				"reference_doctype": "Sales Invoice",
				"reference_name": sales_invoice.name,
				"docstatus": 1,
			},
			fields=["name", "paid_amount"],
		)

		total_existing_payments = sum([flt(pe.paid_amount) for pe in existing_payments])
		remaining_amount = flt(amount_paid) - total_existing_payments

		if remaining_amount <= 0:
			return {"status": "info", "message": "Payment already recorded"}

		# Get the latest payment from Xero for reference
		latest_payment = max(payments, key=lambda x: x.get("UpdatedDateUTC", ""))
		payment_date = latest_payment.get("Date", "")

		# Parse Xero date format
		if payment_date:
			# Xero date format: /Date(1234567890000+0000)/
			import re

			date_match = re.search(r"/Date\((\d+)", payment_date)
			if date_match:
				timestamp = int(date_match.group(1)) / 1000
				payment_date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
			else:
				payment_date = frappe.utils.today()
		else:
			payment_date = frappe.utils.today()

		# Create Payment Entry
		payment_entry = frappe.new_doc("Payment Entry")
		payment_entry.payment_type = "Receive"
		payment_entry.party_type = "Customer"
		payment_entry.party = sales_invoice.customer
		payment_entry.mode_of_payment = "Cash"
		payment_entry.company = sales_invoice.company
		payment_entry.posting_date = payment_date
		payment_entry.paid_amount = remaining_amount
		payment_entry.received_amount = remaining_amount
		payment_entry.reference_no = latest_payment.get("Reference", f"Xero-{invoice_id[:8]}")
		payment_entry.reference_date = payment_date
		payment_entry.remarks = f"Payment synced from Xero for Invoice {sales_invoice.name}"

		# Set accounts
		company_doc = frappe.get_doc("Company", sales_invoice.company)

		# Get the default cash account for the company
		paid_to_account = None
		if hasattr(company_doc, "default_cash_account") and company_doc.default_cash_account:
			paid_to_account = company_doc.default_cash_account
		elif hasattr(company_doc, "default_bank_account") and company_doc.default_bank_account:
			paid_to_account = company_doc.default_bank_account
		else:
			# Fallback: find the first cash/bank account for this company
			cash_accounts = frappe.get_all(
				"Account",
				filters={
					"company": sales_invoice.company,
					"account_type": ["in", ["Cash", "Bank"]],
					"is_group": 0,
				},
				fields=["name"],
				limit=1,
			)
			if cash_accounts:
				paid_to_account = cash_accounts[0].name

		if not paid_to_account:
			return {
				"status": "error",
				"message": f"No cash/bank account found for company {sales_invoice.company}",
			}

		payment_entry.paid_to = paid_to_account

		# Get customer's receivable account
		customer_doc = frappe.get_doc("Customer", sales_invoice.customer)
		if hasattr(customer_doc, "accounts") and customer_doc.accounts:
			for acc in customer_doc.accounts:
				if acc.company == sales_invoice.company:
					payment_entry.paid_from = acc.account
					break

		if not payment_entry.paid_from:
			# Fallback to default receivable account
			receivable_accounts = frappe.get_all(
				"Account",
				filters={"company": sales_invoice.company, "account_type": "Receivable", "is_group": 0},
				fields=["name"],
				limit=1,
			)
			if receivable_accounts:
				payment_entry.paid_from = receivable_accounts[0].name
			else:
				return {
					"status": "error",
					"message": f"No receivable account found for company {sales_invoice.company}",
				}

		# Add reference to the Sales Invoice
		payment_entry.append(
			"references",
			{
				"reference_doctype": "Sales Invoice",
				"reference_name": sales_invoice.name,
				"allocated_amount": remaining_amount,
			},
		)

		# Save and submit
		payment_entry.insert()
		payment_entry.submit()

		return {
			"status": "success",
			"message": f"Payment Entry {payment_entry.name} created",
			"payment_entry": payment_entry.name,
		}

	except Exception as e:
		frappe.log_error("Xero Payment Entry Creation", f"Error creating payment entry: {str(e)}")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def create_invoice(doc, method=None, update=False):
	"""Create invoice in Xero"""
	try:
		client = get_xero_client()

		# Get the Sales Invoice document
		if isinstance(doc, str):
			invoice = frappe.get_doc("Sales Invoice", doc)
		elif hasattr(doc, "doctype") and doc.doctype == "Sales Invoice":
			invoice = doc

		# Get customer contact ID from Xero
		contact_id = get_customer_contact_id(invoice.customer)
		if not contact_id:
			frappe.throw(f"No Xero contact ID found for customer: {invoice.customer}")

		# Prepare line items
		line_items = []
		for item in invoice.items:
			line_item = {
				"Description": item.description or item.item_name,
				"Quantity": str(item.qty),
				"UnitAmount": str(item.rate),
				"AccountCode": item.get("custom_account_code") or "200",
			}

			# Add discount rate if available
			if item.get("discount_percentage"):
				line_item["DiscountRate"] = str(item.discount_percentage)

			line_items.append(line_item)

		# Prepare invoice data
		invoice_data = {
			"Type": "ACCREC",
			"Contact": {"ContactID": contact_id},
			"InvoiceNumber": invoice.name,  # Use Sales Invoice name as invoice number
			"DateString": invoice.posting_date.strftime("%Y-%m-%d") if invoice.posting_date else None,
			"DueDateString": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else None,
			"LineAmountTypes": "Exclusive",
			"LineItems": line_items,
			"Reference": invoice.name,
			"Status": "AUTHORISED",
		}

		# Add currency if different from base currency
		if invoice.currency and invoice.currency != frappe.get_cached_value(
			"Company", invoice.company, "default_currency"
		):
			invoice_data["CurrencyCode"] = invoice.currency

		data = {"Invoices": [invoice_data]}
		if update:
			response = client.make_request(
				"POST", f"/Invoices/{invoice.custom_xero_invoice_number}", data=data
			)
		else:
			response = client.make_request("POST", "/Invoices", data=data)

		if response and "Invoices" in response:
			xero_invoice = response["Invoices"][0]

			return {
				"status": "success",
				"data": xero_invoice,
				"message": f"Invoice created in Xero with ID: {xero_invoice.get('InvoiceID')}",
			}

		return {"status": "error", "message": "Failed to create invoice in Xero"}

	except Exception as e:
		frappe.log_error("Xero Create Invoice", f"Failed to create invoice in Xero: {str(e)}")
		frappe.throw(f"Failed to create invoice in Xero: {str(e)}")


@frappe.whitelist()
def fetch_xero_contacts(contact_person):
	"""Fetch contacts from Xero and filter by similar names to contact person"""
	try:
		client = get_xero_client()
		response = client.make_request("GET", "/Contacts")

		xero_contacts = response.get("Contacts", [])
		contact_doc = frappe.get_doc("Contact", contact_person)
		contact_name = contact_doc.name or ""

		# Filter contacts with similar names
		similar_contacts = []
		for contact in xero_contacts:
			xero_name = contact.get("Name", "").lower()
			contact_name_lower = contact_name.lower()

			# Simple similarity check - contains or partial match
			if (
				xero_name in contact_name_lower
				or contact_name_lower in xero_name
				or any(word in xero_name for word in contact_name_lower.split() if len(word) > 2)
			):
				similar_contacts.append(contact)

		return similar_contacts

	except Exception as e:
		frappe.log_error(f"Failed to fetch Xero contacts: {str(e)}", "Fetch Xero Contacts")
		return []


@frappe.whitelist()
def create_contact_and_map(contact_person, sales_invoice):
	"""Create contact in Xero using ERPNext contact details and map it"""
	try:
		# Get contact details from ERPNext
		contact_doc = frappe.get_doc("Contact", contact_person)

		# Check customer and supplier links
		is_customer = False
		is_supplier = False

		if hasattr(contact_doc, "links") and contact_doc.links:
			for link in contact_doc.links:
				if link.link_doctype == "Customer":
					is_customer = True
				if link.link_doctype == "Supplier":
					is_supplier = True

		# Create contact in Xero
		client = get_xero_client()
		contact_data = {
			"Name": contact_doc.name,
			"FirstName": contact_doc.first_name or "",
			"LastName": contact_doc.last_name or "",
			"EmailAddress": contact_doc.email_id or "",
			"AccountNumber": contact_doc.custom_account_number or contact_doc.name,
			"IsCustomer": is_customer,
			"IsSupplier": is_supplier,
			"Addresses": [
				{
					"AddressType": "STREET",
					"AddressLine1": contact_doc.address or "",
				}
			],
			"Phones": [
				{"PhoneType": "DEFAULT", "PhoneNumber": contact_doc.phone or contact_doc.mobile_no or ""}
			],
		}

		data = {"Contacts": [contact_data]}
		response = client.make_request("POST", "/Contacts", data=data)

		if response and response.get("Contacts"):
			contact_id = response["Contacts"][0].get("ContactID")

			# Map the contact
			map_result = map_contact_to_xero(contact_id, contact_person, sales_invoice)

			if map_result:
				return {
					"status": "success",
					"contact_id": contact_id,
					"message": "Contact created and mapped successfully",
				}

		return {"status": "error", "message": "Failed to create contact in Xero"}

	except Exception as e:
		frappe.log_error(f"Failed to create and map contact: {str(e)}", "Create Contact and Map")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def map_contact_to_xero(contact_id, contact_person, sales_invoice):
	"""Map contact to Xero by setting contact_id in Contact and Sales Invoice"""
	try:
		# Update Contact with Xero contact ID
		contact_doc = frappe.get_doc("Contact", contact_person)
		contact_doc.custom_contact_id = contact_id
		contact_doc.custom_send_to_xero = 1
		contact_doc.save()

		# Update Sales Invoice with Xero contact ID
		sales_invoice_doc = frappe.get_doc("Sales Invoice", sales_invoice)
		sales_invoice_doc.custom_contact_id = contact_id
		sales_invoice_doc.save()

		return True

	except Exception as e:
		frappe.log_error(f"Failed to map contact: {str(e)}", "Map Contact to Xero")
		return False


@frappe.whitelist()
def cancel_invoice_in_xero(xero_invoice_id):
	"""Cancel/void an invoice in Xero"""
	try:
		client = get_xero_client()

		# First, get the current invoice to check its status
		response = client.make_request("GET", f"/Invoices/{xero_invoice_id}")

		if not response or "Invoices" not in response:
			return {"status": "error", "message": "Invoice not found in Xero"}

		current_invoice = response["Invoices"][0]
		current_status = current_invoice.get("Status")

		# Check if invoice can be voided
		if current_status in ["PAID", "VOIDED"]:
			return {
				"status": "info",
				"message": f"Invoice cannot be cancelled as it is already {current_status}",
			}

		# Void the invoice
		invoice_data = {"InvoiceID": xero_invoice_id, "Status": "VOIDED"}

		data = {"Invoices": [invoice_data]}
		response = client.make_request("POST", "/Invoices", data=data)

		if response and "Invoices" in response:
			voided_invoice = response["Invoices"][0]
			return {
				"status": "success",
				"message": f"Invoice {xero_invoice_id} cancelled successfully in Xero",
				"data": voided_invoice,
			}

		return {"status": "error", "message": "Failed to cancel invoice in Xero"}

	except Exception as e:
		frappe.log_error(
			f"Failed to cancel invoice {xero_invoice_id} in Xero: {str(e)}", "Xero Cancel Invoice"
		)
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_customer_contact_id(customer):
	"""Get customer contact ID from Xero"""
	try:
		dynamic_links = frappe.get_all(
			"Dynamic Link",
			filters={"link_doctype": "Customer", "link_name": customer, "parenttype": "Contact"},
			fields=["parent"],
			limit=1,
		)

		if dynamic_links:
			contact_name = dynamic_links[0].parent
			contact = frappe.get_doc("Contact", contact_name)
			return contact.get("custom_contact_id")

		return None
	except Exception as e:
		frappe.throw("Error getting contact id for the selected customer")
