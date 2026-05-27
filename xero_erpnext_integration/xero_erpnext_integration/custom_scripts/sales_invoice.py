import frappe
from frappe import _


def before_submit(doc, method=None):
	"""Validate before submitting Sales Invoice"""
	if doc.custom_do_not_sync_to_xero:
		return

	if doc.custom_contact_id:
		return

	if not doc.customer or not doc.contact_person:
		frappe.throw(
			_(
				"Customer and Contact Person are required for Xero integration.<br>"
				"Please set these fields or check 'Do not Sync to Xero' to proceed."
			)
		)

	frappe.throw(
		_(
			"Xero Contact ID is not found for customer: {0}<br><br>"
			"Please click the 'Update Contact' button to map or create the contact in Xero."
		).format(doc.customer)
	)


# C3 fix: removed @frappe.whitelist() — on_submit is a doc event handler, not a public API endpoint.
# It is also currently commented out in hooks.py. The Xero sync is triggered via workflow action button,
# not via this doc event.
def on_submit(doc, method=None):
	"""Create invoice in Xero after submission"""
	before_submit(doc, method)

	if doc.custom_do_not_sync_to_xero:
		return

	try:
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import create_invoice

		result = create_invoice(doc.name)

		if result and result.get("status") == "success":
			xero_invoice_id = result.get("data", {}).get("InvoiceID")
			if xero_invoice_id:
				frappe.db.set_value("Sales Invoice", doc.name, "custom_xero_invoice_number", xero_invoice_id)
				# B5 fix: removed frappe.db.commit() — framework manages the transaction lifecycle.
				# An explicit commit mid-hook commits partial state that cannot be rolled back on error.

				frappe.msgprint(
					_("Invoice created successfully in Xero"), title=_("Success"), indicator="green"
				)
		else:
			error_msg = result.get("message", "Unknown error") if result else "No response from Xero"
			frappe.log_error(
				title="Xero Create Invoice",
				message=f"Failed to create invoice {doc.name} in Xero: {error_msg}",
			)
			frappe.throw(_("Failed to create invoice in Xero: {0}").format(error_msg))

	except Exception as e:
		frappe.log_error(
			title="Xero Create Invoice",
			message=f"Error creating invoice {doc.name} in Xero: {e!s}",
		)
		frappe.throw(_("Error creating invoice in Xero: {0}").format(str(e)))


def on_cancel(doc, method=None):
	"""Cancel invoice in Xero when cancelled in ERPNext"""
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
				title="Xero Cancel Invoice",
				message=f"Failed to cancel invoice {doc.name} in Xero: {result.get('message') if result else 'Unknown error'}",
			)
			frappe.msgprint(
				_(
					"Warning: Invoice was cancelled in ERPNext but could not be cancelled in Xero. Please check Error Log."
				),
				title=_("Warning"),
				indicator="orange",
			)
	except Exception as e:
		frappe.log_error(
			title="Xero Cancel Invoice",
			message=f"Error cancelling invoice {doc.name} in Xero: {e!s}",
		)
		frappe.msgprint(
			_(
				"Warning: Invoice was cancelled in ERPNext but could not be cancelled in Xero. Please check Error Log."
			),
			title=_("Warning"),
			indicator="orange",
		)
