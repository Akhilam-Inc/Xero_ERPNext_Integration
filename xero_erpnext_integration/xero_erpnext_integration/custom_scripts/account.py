import frappe
from frappe import _


@frappe.whitelist()
def send_tax_account_to_xero(doc_name: str):
	"""Form-button entry point: push a single tax Account to Xero TaxRates."""
	from xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate import create_tax_rate

	doc = frappe.get_doc("Account", doc_name)

	if (doc.account_type or "") != "Tax":
		frappe.throw(_("Only accounts with account_type='Tax' can be synced to Xero."))

	if doc.get("custom_xero_tax_type"):
		frappe.msgprint(
			_("Account already synced to Xero (TaxType {0})").format(doc.custom_xero_tax_type),
			title=_("Info"),
			indicator="blue",
		)
		return {"status": "info", "tax_type": doc.custom_xero_tax_type}

	result = create_tax_rate(doc.name)
	if result and result.get("status") == "success":
		frappe.msgprint(result.get("message"), title=_("Success"), indicator="green")
	return result


def on_update(doc, method=None):
	"""Auto-sync a Tax account to Xero on save when:
	- account_type == "Tax"
	- custom_send_to_xero is checked
	- custom_xero_tax_type is empty (not yet synced)

	On success, also mirrors the Xero values (TaxType, Report Tax Type) back onto
	the in-memory doc so the client-side response reflects the synced state
	without needing a manual reload.
	"""
	if (doc.get("account_type") or "") != "Tax":
		return
	if not doc.get("custom_send_to_xero"):
		return
	if doc.get("custom_xero_tax_type"):
		return

	# Only do the network call if the Xero integration is enabled to avoid
	# crashing during normal Account edits in environments without a Xero setup.
	enabled = frappe.db.get_single_value("Xero Settings", "enable")
	if not enabled:
		return

	try:
		from xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate import create_tax_rate

		result = create_tax_rate(doc.name) or {}
	except Exception as e:
		frappe.log_error(
			title="Xero Tax Rate Sync",
			message=f"Failed to auto-sync Account {doc.name} to Xero: {e!s}",
		)
		frappe.msgprint(
			_("Could not sync tax account to Xero: {0}").format(e),
			title=_("Xero Tax Rate Sync"),
			indicator="orange",
		)
		return

	if result.get("status") != "success":
		message = result.get("message") or _("Unknown error from Xero")
		frappe.msgprint(
			_("Could not sync tax account to Xero: {0}").format(message),
			title=_("Xero Tax Rate Sync"),
			indicator="orange",
		)
		return

	xero_data = result.get("data") or {}
	tax_type = result.get("tax_type") or xero_data.get("TaxType")
	report_tax_type = result.get("report_tax_type") or xero_data.get("ReportTaxType")

	# Mirror DB-side updates onto the in-memory doc so the client form picks them
	# up from the save response (no extra reload required).
	if tax_type:
		doc.custom_xero_tax_type = tax_type
	if report_tax_type:
		doc.custom_xero_report_tax_type = report_tax_type
	if not doc.get("custom_send_to_xero"):
		doc.custom_send_to_xero = 1

	parts = []
	if tax_type:
		parts.append(_("TaxType: {0}").format(tax_type))
	if report_tax_type:
		parts.append(_("Report Tax Type: {0}").format(report_tax_type))
	suffix = f" ({', '.join(parts)})" if parts else ""

	frappe.msgprint(
		_("Account synced successfully to Xero") + suffix,
		title=_("Xero Sync"),
		indicator="green",
		alert=True,
	)
