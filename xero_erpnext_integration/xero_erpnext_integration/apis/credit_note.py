from __future__ import annotations

from datetime import datetime, timedelta, timezone

import frappe
from frappe.utils import flt

from .base import get_xero_client
from .item import ensure_xero_items_for_lines
from .sales_invoice import build_xero_line_item, get_customer_contact_id, get_line_amount_types


def _as_xero_date_string(d) -> str | None:
	if not d:
		return None
	if isinstance(d, str):
		return d
	return d.strftime("%Y-%m-%d")


def _xero_where_updated_since(hours: int) -> str:
	# Xero query format: UpdatedDateUTC>=DateTime(2026,05,08,10,00,00)
	dt = datetime.now(timezone.utc) - timedelta(hours=hours)
	return f"UpdatedDateUTC>=DateTime({dt.year},{dt.month:02d},{dt.day:02d},{dt.hour:02d},{dt.minute:02d},{dt.second:02d})"


@frappe.whitelist()
def create_credit_note(sales_return: str, update: bool = False):
	"""
	Create/Update a Xero Credit Note from an ERPNext Sales Invoice Return (Sales Invoice with is_return=1).
	Stores linkage back on the return invoice:
	- custom_xero_credit_note_id / number / status
	"""
	sr = frappe.get_doc("Sales Invoice", sales_return)

	if sr.docstatus != 1:
		frappe.throw("Sales Return must be submitted before syncing to Xero.")
	if not getattr(sr, "is_return", 0):
		frappe.throw("Selected Sales Invoice is not a return (is_return=1).")
	if getattr(sr, "custom_do_not_sync_to_xero", 0):
		frappe.throw("Xero sync is disabled for this Sales Return.")

	contact_id = get_customer_contact_id(sr.customer)
	if not contact_id:
		frappe.throw(f"No Xero contact ID found for customer: {sr.customer}")

	# Decide LineAmountTypes once for the document, based on the return's taxes
	line_amount_types = get_line_amount_types(sr)

	client = get_xero_client()
	item_code_map = ensure_xero_items_for_lines(sr.items, client=client)

	line_items = []
	for item in sr.items:
		qty = abs(flt(item.qty))
		if qty == 0:
			continue
		# Build the standard ItemCode + TaxType payload, then override the quantity
		# with the positive value (Xero credit notes use positive quantities).
		line_item = build_xero_line_item(
			item, sr, line_amount_types=line_amount_types, item_code_map=item_code_map
		)
		line_item["Quantity"] = str(qty)
		line_items.append(line_item)

	if not line_items:
		frappe.throw("Sales Return must have at least one item with non-zero quantity.")

	credit_note_data = {
		"Type": "ACCRECCREDIT",
		"Contact": {"ContactID": contact_id},
		"DateString": _as_xero_date_string(sr.posting_date),
		"LineAmountTypes": line_amount_types,
		"LineItems": line_items,
		"Reference": f"ERPNext Sales Return: {sr.name} | ReturnAgainst: {sr.return_against or ''}",
		"Status": "AUTHORISED",
	}

	# Currency (if needed)
	if sr.currency and sr.company:
		company_currency = frappe.get_cached_value("Company", sr.company, "default_currency")
		if sr.currency != company_currency:
			credit_note_data["CurrencyCode"] = sr.currency

	data = {"CreditNotes": [credit_note_data]}

	if update and getattr(sr, "custom_xero_credit_note_id", None):
		response = client.make_request("POST", f"/CreditNotes/{sr.custom_xero_credit_note_id}", data=data)
	else:
		response = client.make_request("POST", "/CreditNotes", data=data)

	if response and response.get("CreditNotes"):
		cn = response["CreditNotes"][0]
		frappe.db.set_value("Sales Invoice", sr.name, "custom_xero_credit_note_id", cn.get("CreditNoteID"))
		frappe.db.set_value(
			"Sales Invoice", sr.name, "custom_xero_credit_note_number", cn.get("CreditNoteNumber")
		)
		frappe.db.set_value("Sales Invoice", sr.name, "custom_xero_credit_note_status", cn.get("Status"))
		return {"status": "success", "data": cn}

	return {"status": "error", "message": "Failed to create credit note in Xero"}


@frappe.whitelist()
def push_pending_sales_returns(limit: int = 50):
	"""Cron: push submitted Sales Returns (is_return=1) not yet synced to Xero."""
	limit = int(limit or 50)
	to_sync = frappe.get_all(
		"Sales Invoice",
		filters=[
			["docstatus", "=", 1],
			["is_return", "=", 1],
			["custom_do_not_sync_to_xero", "=", 0],
			["custom_xero_credit_note_id", "is", "not set"],
		],
		fields=["name"],
		limit=limit,
	)

	out = {"created": [], "failed": []}
	for row in to_sync:
		try:
			res = create_credit_note(row.name, update=False)
			if res and res.get("status") == "success":
				out["created"].append(row.name)
			else:
				out["failed"].append(
					{"name": row.name, "error": (res or {}).get("message") or "Unknown error"}
				)
		except Exception as e:
			out["failed"].append({"name": row.name, "error": str(e)})

	if out["failed"]:
		frappe.log_error(title="Xero Credit Note Push", message=frappe.as_json(out))
	return out


@frappe.whitelist()
def sync_selected_sales_returns(invoices):
	"""
	Bulk sync selected ERPNext Sales Returns to Xero as Credit Notes.

	Only sync returns that:
	- are submitted (`docstatus == 1`)
	- have `custom_do_not_sync_to_xero` unchecked
	- are returns (`is_return == 1`)
	- have no `custom_xero_credit_note_id` yet
	"""
	invoice_names = frappe.parse_json(invoices) or []
	if not isinstance(invoice_names, list):
		frappe.throw("Invalid invoices payload")

	valid_names = [n for n in invoice_names if n]
	results = {"created": [], "skipped": [], "failed": []}

	if not valid_names:
		return results

	# Batch-fetch all screening fields in one query — avoids N+1 (AKH-02)
	sr_rows = frappe.get_all(
		"Sales Invoice",
		filters=[["name", "in", valid_names]],
		fields=["name", "docstatus", "is_return", "custom_do_not_sync_to_xero", "custom_xero_credit_note_id"],
	)
	sr_map = {row.name: row for row in sr_rows}

	for name in valid_names:
		try:
			sr = sr_map.get(name)
			if not sr:
				results["failed"].append({"name": name, "error": "Sales Return not found"})
				continue

			if sr.docstatus != 1:
				results["skipped"].append({"name": name, "reason": "Not submitted"})
				continue
			if not sr.is_return:
				results["skipped"].append({"name": name, "reason": "Not a return"})
				continue
			if sr.custom_do_not_sync_to_xero:
				results["skipped"].append({"name": name, "reason": "Xero sync disabled"})
				continue
			if sr.custom_xero_credit_note_id:
				results["skipped"].append({"name": name, "reason": "Already synced"})
				continue

			# create_credit_note loads the full doc internally (needs items, taxes, etc.)
			res = create_credit_note(name, update=False)
			if not res or res.get("status") != "success":
				results["failed"].append(
					{"name": name, "error": (res or {}).get("message") or "Unknown error"}
				)
				continue

			cn = res.get("data") or {}
			results["created"].append(
				{"name": name, "xero_credit_note_id": cn.get("CreditNoteID")}
			)

		except Exception as e:
			results["failed"].append({"name": name, "error": str(e)})

	return results


def _match_sales_invoice_by_xero_invoice_id(xero_invoice_id: str) -> str | None:
	if not xero_invoice_id:
		return None
	return frappe.db.get_value("Sales Invoice", {"custom_xero_invoice_number": xero_invoice_id}, "name")


def _get_allocation_invoice_id(credit_note: dict) -> str | None:
	allocs = credit_note.get("Allocations") or []
	for a in allocs:
		inv = a.get("Invoice") or {}
		if inv.get("InvoiceID"):
			return inv.get("InvoiceID")
	return None


@frappe.whitelist()
def pull_updated_credit_notes(hours: int = 2, limit: int = 100):
	"""
	Cron: pull recently updated Xero Credit Notes into ERPNext as Sales Invoice Returns.
	Idempotency: uses Sales Invoice.custom_xero_credit_note_id.
	"""
	hours = int(hours or 2)
	limit = int(limit or 100)

	client = get_xero_client()
	where = _xero_where_updated_since(hours)
	response = client.make_request("GET", "/CreditNotes", params={"where": where})
	credit_notes = (response or {}).get("CreditNotes", [])[:limit]

	out = {"created": [], "skipped": [], "failed": []}

	# Batch-fetch all already-imported credit note IDs in one query — avoids N+1 (AKH-02)
	all_cn_ids = [cn.get("CreditNoteID") for cn in credit_notes if cn.get("CreditNoteID")]
	already_imported: dict[str, str] = {}
	if all_cn_ids:
		existing_rows = frappe.get_all(
			"Sales Invoice",
			filters=[["custom_xero_credit_note_id", "in", all_cn_ids]],
			fields=["name", "custom_xero_credit_note_id"],
		)
		already_imported = {row.custom_xero_credit_note_id: row.name for row in existing_rows}

	for cn in credit_notes:
		try:
			cn_id = cn.get("CreditNoteID")
			if not cn_id:
				continue

			# already imported?
			if cn_id in already_imported:
				out["skipped"].append({
					"xero_credit_note_id": cn_id,
					"reason": "Already imported",
					"sales_return": already_imported[cn_id],
				})
				continue

			xero_invoice_id = _get_allocation_invoice_id(cn)
			erp_invoice = _match_sales_invoice_by_xero_invoice_id(xero_invoice_id)
			if not erp_invoice:
				out["skipped"].append(
					{"xero_credit_note_id": cn_id, "reason": "No matching ERPNext invoice for allocation"}
				)
				continue

			sr_name = _create_sales_return_from_invoice(erp_invoice, cn)
			out["created"].append({"xero_credit_note_id": cn_id, "sales_return": sr_name})
		except Exception as e:
			out["failed"].append({"xero_credit_note_id": cn.get("CreditNoteID"), "error": str(e)})

	if out["failed"]:
		frappe.log_error(title="Xero Credit Note Pull", message=frappe.as_json(out))
	return out


def _create_sales_return_from_invoice(invoice_name: str, credit_note: dict) -> str:
	"""
	Create a Sales Invoice Return against an existing Sales Invoice, best-effort mapping lines.
	Creates and submits the return if it has at least one negative qty line.
	"""
	from erpnext.controllers.sales_and_purchase_return import make_return_doc

	si = frappe.get_doc("Sales Invoice", invoice_name)
	return_doc = make_return_doc("Sales Invoice", si.name)

	# Keep it simple: map by Description and override qty/rate from Xero CN lines when matched.
	xero_lines = credit_note.get("LineItems") or []
	xero_by_desc = {}
	for li in xero_lines:
		desc = (li.get("Description") or "").strip().lower()
		if desc:
			xero_by_desc[desc] = li

	mapped_any = False
	for item in return_doc.items:
		desc = (item.description or item.item_name or "").strip().lower()
		xli = xero_by_desc.get(desc)
		if not xli:
			continue

		qty = flt(xli.get("Quantity") or 0)
		unit_amount = flt(xli.get("UnitAmount") or 0)
		if qty <= 0:
			continue

		item.qty = -abs(qty)
		item.rate = unit_amount
		mapped_any = True

	if not mapped_any:
		# If we can't map lines, do not submit a broken return; keep as draft for manual fix.
		return_doc.flags.ignore_mandatory = True

	return_doc.is_return = 1
	return_doc.return_against = si.name
	return_doc.insert(ignore_permissions=True)

	# Store linkage from Xero CN
	frappe.db.set_value(
		"Sales Invoice", return_doc.name, "custom_xero_credit_note_id", credit_note.get("CreditNoteID")
	)
	frappe.db.set_value(
		"Sales Invoice",
		return_doc.name,
		"custom_xero_credit_note_number",
		credit_note.get("CreditNoteNumber"),
	)
	frappe.db.set_value(
		"Sales Invoice", return_doc.name, "custom_xero_credit_note_status", credit_note.get("Status")
	)

	if mapped_any:
		return_doc.submit(ignore_permissions=True)

	return return_doc.name
