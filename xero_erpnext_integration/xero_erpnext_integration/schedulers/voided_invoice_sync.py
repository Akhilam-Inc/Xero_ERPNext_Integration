from datetime import datetime, timedelta

import frappe
from frappe.utils import get_datetime, getdate


def sync_voided_invoices():
	"""Check for voided invoices from Xero today and cancel them in ERPNext"""
	try:
		from ..apis.base import get_xero_client

		client = get_xero_client()
		if not client:
			frappe.log_error(title="Voided Invoice Sync", message="Xero client not available")
			return

		today = getdate()

		where_clause = f'Status=="VOIDED" AND Date >= DateTime({today.year}, {today.month}, {today.day})'
		response = client.make_request("GET", f"/Invoices?where={where_clause}")

		if not response or "Invoices" not in response:
			frappe.log_error(title="Voided Invoice Sync", message="No response from Xero for voided invoices")
			return

		voided_invoices = response["Invoices"]

		# C1 fix: informational messages belong in logger, not Error Log
		frappe.logger().info(
			f"Voided Invoice Sync: found {len(voided_invoices)} voided invoices in Xero for today"
		)

		for xero_invoice in voided_invoices:
			process_voided_invoice(xero_invoice)

	except Exception as e:
		frappe.log_error(title="Voided Invoice Sync", message=f"Error in voided invoice sync: {e!s}")


def process_voided_invoice(xero_invoice):
	"""Process a single voided invoice from Xero"""
	try:
		invoice_id = xero_invoice.get("InvoiceID")
		invoice_number = xero_invoice.get("InvoiceNumber")

		# B3 fix: ignore_permissions — runs in scheduler context (background worker)
		sales_invoices = frappe.get_all(
			"Sales Invoice",
			filters={"custom_xero_invoice_number": invoice_id},
			fields=["name", "customer", "docstatus", "grand_total"],
			limit=1,
			ignore_permissions=True,
		)

		if not sales_invoices:
			sales_invoices = frappe.get_all(
				"Sales Invoice",
				filters={"custom_xero_invoice_number": invoice_number},
				fields=["name", "customer", "docstatus", "grand_total"],
				limit=1,
				ignore_permissions=True,
			)

		if not sales_invoices:
			frappe.log_error(
				title="Voided Invoice Sync",
				message=f"No ERPNext invoice found for Xero invoice {invoice_id} ({invoice_number})",
			)
			return

		sales_invoice = sales_invoices[0]

		if sales_invoice["docstatus"] == 2:
			frappe.logger().info(f"Voided Invoice Sync: invoice {sales_invoice['name']} is already cancelled")
			return

		if sales_invoice["docstatus"] != 1:
			frappe.log_error(
				title="Voided Invoice Sync",
				message=f"Invoice {sales_invoice['name']} is not submitted, cannot cancel",
			)
			return

		cancel_invoice_in_erpnext(sales_invoice, invoice_id, invoice_number)

	except Exception as e:
		frappe.log_error(
			title="Voided Invoice Sync",
			message=f"Error processing voided invoice {xero_invoice.get('InvoiceID', 'Unknown')}: {e!s}",
		)


def cancel_invoice_in_erpnext(sales_invoice, xero_invoice_id, xero_invoice_number):
	"""Cancel a sales invoice in ERPNext"""
	try:
		sales_invoice_doc = frappe.get_doc("Sales Invoice", sales_invoice["name"])

		# B4 fix: cancel() runs in scheduler context — frappe.session.user is "Administrator"
		# but ignore_permissions ensures no permission check failure
		sales_invoice_doc.flags.ignore_permissions = True
		sales_invoice_doc.cancel()

		comment_text = "Invoice cancelled automatically via scheduler due to VOID status in Xero"
		if xero_invoice_id:
			comment_text += f" (Invoice ID: {xero_invoice_id}"
			if xero_invoice_number:
				comment_text += f", Number: {xero_invoice_number}"
			comment_text += ")"

		sales_invoice_doc.add_comment("Comment", comment_text)

		# C1 fix: use logger for success messages — not Error Log
		frappe.logger().info(
			f"Voided Invoice Sync: cancelled invoice {sales_invoice['name']} due to VOID in Xero"
		)

	except Exception as e:
		frappe.log_error(
			title="Voided Invoice Sync",
			message=f"Error cancelling invoice {sales_invoice['name']}: {e!s}",
		)
