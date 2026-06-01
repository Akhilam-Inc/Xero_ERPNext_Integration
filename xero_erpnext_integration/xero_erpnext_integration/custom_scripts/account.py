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

		create_tax_rate(doc.name)
	except Exception as e:
		frappe.log_error(
			title="Xero Tax Rate Sync",
			message=f"Failed to auto-sync Account {doc.name} to Xero: {e!s}",
		)
