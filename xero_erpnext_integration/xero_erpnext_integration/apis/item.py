"""
Ensure ERPNext Items exist in Xero before syncing invoice/credit-note lines.

Xero rejects invoice LineItems when ItemCode is set to a code that does not
exist in the Xero Items list. This module creates missing items automatically
(or reuses an existing Xero item with the same Code).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from .base import get_xero_client


def _xero_item_code(item_code: str) -> str:
	"""Normalize an ERPNext item code for Xero (max 30 chars, trimmed)."""
	code = (item_code or "").strip()
	if not code:
		return ""
	# Xero item codes are short identifiers; truncate if needed.
	return code[:30]


def _item_exists_in_xero(client, code: str) -> dict | None:
	"""Return the Xero Item dict if `code` exists, else None."""
	# Xero OData filter — escape double quotes in code
	safe = code.replace('"', "")
	where = f'Code=="{safe}"'
	try:
		response = client.make_request("GET", "/Items", params={"where": where}) or {}
	except Exception as e:
		frappe.log_error(title="Xero Item Lookup", message=f"Failed to check item {code!r} in Xero: {e!s}")
		return None

	for row in response.get("Items") or []:
		if (row.get("Code") or "").strip() == code:
			return row
	return None


def _build_xero_item_payload(item_doc, code: str) -> dict:
	"""Build the JSON body for POST /Items."""
	name = (item_doc.item_name or item_doc.name or code)[:50]
	description = (item_doc.description or item_doc.item_name or name)[:4000]

	payload = {
		"Code": code,
		"Name": name,
		"Description": description,
		"IsSold": True,
		"IsPurchased": bool(item_doc.is_purchase_item),
	}

	# Optional sales defaults (invoice lines still send their own UnitAmount).
	# Income account lives on the Item Default child table (Item and Item Group), not on Item Group directly.
	sales_account = frappe.db.get_value(
		"Item Default",
		{"parent": item_doc.name, "parenttype": "Item"},
		"income_account",
	)
	if not sales_account and item_doc.get("item_group"):
		sales_account = frappe.db.get_value(
			"Item Default",
			{"parent": item_doc.item_group, "parenttype": "Item Group"},
			"income_account",
		)

	account_code = None
	if sales_account:
		if frappe.db.has_column("Account", "account_number"):
			account_code = frappe.db.get_value("Account", sales_account, "account_number")
		if not account_code and frappe.db.has_column("Account", "custom_account_code"):
			account_code = frappe.db.get_value("Account", sales_account, "custom_account_code")

	if account_code or flt(item_doc.standard_rate):
		payload["SalesDetails"] = {}
		if account_code:
			payload["SalesDetails"]["AccountCode"] = str(account_code)[:10]
		if flt(item_doc.standard_rate):
			payload["SalesDetails"]["UnitPrice"] = flt(item_doc.standard_rate)

	return payload


def _save_item_mapping(item_code: str, xero_code: str):
	if not frappe.db.exists("Item", item_code):
		return
	if frappe.db.has_column("Item", "custom_xero_item_code"):
		frappe.db.set_value("Item", item_code, "custom_xero_item_code", xero_code)


@frappe.whitelist()
def ensure_xero_item(item_code: str, client=None) -> str | None:
	"""
	Ensure a single ERPNext Item exists in Xero.

	Returns the Xero Item Code to use on invoice lines, or None if `item_code` is empty.
	"""
	code = _xero_item_code(item_code)
	if not code:
		return None

	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} does not exist in ERPNext").format(item_code))

	# Reuse stored mapping
	if frappe.db.has_column("Item", "custom_xero_item_code"):
		mapped = frappe.db.get_value("Item", item_code, "custom_xero_item_code")
		if mapped:
			return mapped

	client = client or get_xero_client()

	existing = _item_exists_in_xero(client, code)
	if existing:
		xero_code = existing.get("Code") or code
		_save_item_mapping(item_code, xero_code)
		return xero_code

	item_doc = frappe.get_doc("Item", item_code)
	payload = _build_xero_item_payload(item_doc, code)
	response = client.make_request("POST", "/Items", data={"Items": [payload]}) or {}

	created = (response.get("Items") or [None])[0]
	if not created:
		frappe.throw(_("Failed to create item {0} in Xero").format(code))

	xero_code = created.get("Code") or code
	_save_item_mapping(item_code, xero_code)
	return xero_code


def ensure_xero_items_for_lines(lines, client=None) -> dict[str, str]:
	"""
	Ensure all distinct `item_code` values on invoice/credit-note lines exist in Xero.

	Returns a map of ERPNext item_code -> Xero Item Code.
	"""
	client = client or get_xero_client()
	codes: set[str] = set()

	for row in lines or []:
		item_code = row.get("item_code") if hasattr(row, "get") else getattr(row, "item_code", None)
		if item_code:
			codes.add(item_code)

	mapping: dict[str, str] = {}
	for item_code in sorted(codes):
		mapping[item_code] = ensure_xero_item(item_code, client=client) or item_code

	return mapping


def resolve_line_item_code(item_row, item_code_map: dict[str, str] | None = None) -> str | None:
	"""Pick the Xero ItemCode for an invoice line (after ensure_xero_items_for_lines)."""
	item_code = item_row.get("item_code") if hasattr(item_row, "get") else getattr(item_row, "item_code", None)
	if not item_code:
		return None

	if item_code_map and item_code in item_code_map:
		return item_code_map[item_code]

	override = item_row.get("custom_xero_item_code") if hasattr(item_row, "get") else None
	if override:
		return override

	if frappe.db.has_column("Item", "custom_xero_item_code"):
		mapped = frappe.db.get_value("Item", item_code, "custom_xero_item_code")
		if mapped:
			return mapped

	return _xero_item_code(item_code)
