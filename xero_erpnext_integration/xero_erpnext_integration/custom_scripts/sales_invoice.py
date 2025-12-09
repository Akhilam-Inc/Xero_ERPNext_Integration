import frappe
from frappe import _


def before_submit(doc, method=None):
	"""Validate before submitting Sales Invoice"""
	# Skip validation if sync is disabled
	if doc.custom_do_not_sync_to_xero:
		return

	# Check if contact ID exists
	if doc.custom_contact_id:
		return

	# Validate required fields for Xero integration
	if not doc.customer or not doc.contact_person:
		frappe.throw(
			_(
				"Customer and Contact Person are required for Xero integration.<br>"
				"Please set these fields or check 'Do not Sync to Xero' to proceed."
			)
		)

	# Contact ID missing but required fields present
	frappe.throw(
		_(
			"Xero Contact ID is not found for customer: {0}<br><br>"
			"Please click the 'Update Contact' button to map or create the contact in Xero."
		).format(doc.customer)
	)


@frappe.whitelist()
def on_submit(doc, method=None, sync_to_xero=None):
	"""Create invoice in Xero after submission"""
	# Skip if sync is disabled
	before_submit(doc, method)
	sync_to_xero = sync_to_xero or doc.custom_do_not_sync_to_xero
	if sync_to_xero:
		return

	try:
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import create_invoice

		result = create_invoice(doc.name)

		if result and result.get("status") == "success":
			# Update invoice with Xero ID
			xero_invoice_id = result.get("data", {}).get("InvoiceID")
			if xero_invoice_id:
				frappe.db.set_value("Sales Invoice", doc.name, "custom_xero_invoice_number", xero_invoice_id)
				frappe.db.commit()

				frappe.msgprint(
					_("Invoice created successfully in Xero"), title=_("Success"), indicator="green"
				)
		else:
			error_msg = result.get("message", "Unknown error") if result else "No response from Xero"
			frappe.log_error(
				f"Failed to create invoice {doc.name} in Xero: {error_msg}", "Xero Create Invoice"
			)
			frappe.throw(_("Failed to create invoice in Xero: {0}").format(error_msg))

	except Exception as e:
		frappe.log_error(f"Error creating invoice {doc.name} in Xero: {str(e)}", "Xero Create Invoice")
		frappe.throw(_("Error creating invoice in Xero: {0}").format(str(e)))


def on_cancel(doc, method=None):
	"""Cancel invoice in Xero when cancelled in ERPNext"""
	# Skip if no Xero integration or invoice not synced
	if not doc.custom_xero_invoice_number or doc.custom_do_not_sync_to_xero:
		return

	try:
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import (
			cancel_invoice_in_xero,
		)

		result = cancel_invoice_in_xero(doc.custom_xero_invoice_number)
		if result and result.get("status") == "success":
			frappe.msgprint(
				_("Invoice cancelled successfully in Xero"), title=_("Success"), indicator="green"
			)
		else:
			frappe.log_error(
				f"Failed to cancel invoice {doc.name} in Xero: {result.get('message') if result else 'Unknown error'}",
				"Xero Cancel Invoice",
			)
			frappe.msgprint(
				_(
					"Warning: Invoice was cancelled in ERPNext but could not be cancelled in Xero. Please check Error Log."
				),
				title=_("Warning"),
				indicator="orange",
			)
	except Exception as e:
		frappe.log_error(f"Error cancelling invoice {doc.name} in Xero: {str(e)}", "Xero Cancel Invoice")
		frappe.msgprint(
			_(
				"Warning: Invoice was cancelled in ERPNext but could not be cancelled in Xero. Please check Error Log."
			),
			title=_("Warning"),
			indicator="orange",
		)
