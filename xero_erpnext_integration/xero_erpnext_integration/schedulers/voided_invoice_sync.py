from datetime import datetime, timedelta

import frappe
from frappe.utils import get_datetime, getdate


def sync_voided_invoices():
	"""Check for voided invoices from Xero today and cancel them in ERPNext"""
	try:
		from ..apis.base import get_xero_client

		# Get Xero client
		client = get_xero_client()
		if not client:
			frappe.log_error("Xero client not available", "Voided Invoice Sync")
			return

		# Get today's date for filtering
		today = getdate()

		# Fetch voided invoices from Xero for today
		where_clause = f'Status=="VOIDED" AND Date >= DateTime({today.year}, {today.month}, {today.day})'
		response = client.make_request("GET", f"/Invoices?where={where_clause}")

		if not response or "Invoices" not in response:
			frappe.log_error("No response from Xero for voided invoices", "Voided Invoice Sync")
			return

		voided_invoices = response["Invoices"]
		frappe.log_error(
			f"Found {len(voided_invoices)} voided invoices in Xero for today", "Voided Invoice Sync"
		)

		for xero_invoice in voided_invoices:
			process_voided_invoice(xero_invoice)

	except Exception as e:
		frappe.log_error(f"Error in voided invoice sync: {str(e)}", "Voided Invoice Sync")


def process_voided_invoice(xero_invoice):
	"""Process a single voided invoice from Xero"""
	try:
		invoice_id = xero_invoice.get("InvoiceID")
		invoice_number = xero_invoice.get("InvoiceNumber")

		# Find corresponding ERPNext Sales Invoice by Xero invoice ID
		sales_invoices = frappe.get_all(
			"Sales Invoice",
			filters={"custom_xero_invoice_number": invoice_id},
			fields=["name", "customer", "docstatus", "grand_total"],
			limit=1,
		)

		if not sales_invoices:
			# Try to find by invoice number if ID search fails
			sales_invoices = frappe.get_all(
				"Sales Invoice",
				filters={"custom_xero_invoice_number": invoice_number},
				fields=["name", "customer", "docstatus", "grand_total"],
				limit=1,
			)

		if not sales_invoices:
			frappe.log_error(
				f"No ERPNext invoice found for Xero invoice {invoice_id} ({invoice_number})",
				"Voided Invoice Sync",
			)
			return

		sales_invoice = sales_invoices[0]

		# Check if invoice is already cancelled
		if sales_invoice["docstatus"] == 2:
			frappe.log_error(f"Invoice {sales_invoice['name']} is already cancelled", "Voided Invoice Sync")
			return

		# Check if invoice is not submitted
		if sales_invoice["docstatus"] != 1:
			frappe.log_error(
				f"Invoice {sales_invoice['name']} is not submitted, cannot cancel", "Voided Invoice Sync"
			)
			return

		# Cancel the invoice in ERPNext
		cancel_invoice_in_erpnext(sales_invoice, invoice_id, invoice_number)

	except Exception as e:
		frappe.log_error(
			f"Error processing voided invoice {xero_invoice.get('InvoiceID', 'Unknown')}: {str(e)}",
			"Voided Invoice Sync",
		)


def cancel_invoice_in_erpnext(sales_invoice, xero_invoice_id, xero_invoice_number):
	"""Cancel a sales invoice in ERPNext"""
	try:
		# Get the Sales Invoice document
		sales_invoice_doc = frappe.get_doc("Sales Invoice", sales_invoice["name"])

		# Cancel the invoice
		sales_invoice_doc.cancel()

		# Add a comment about the cancellation
		sales_invoice_doc.add_comment(
			"Comment",
			f"Invoice cancelled automatically via scheduler due to VOID status in Xero (Invoice ID: {xero_invoice_id}, Number: {xero_invoice_number})",
		)

		frappe.log_error(
			f"Successfully cancelled invoice {sales_invoice['name']} due to VOID in Xero",
			"Voided Invoice Sync Success",
		)

	except Exception as e:
		frappe.log_error(f"Error cancelling invoice {sales_invoice['name']}: {str(e)}", "Voided Invoice Sync")
