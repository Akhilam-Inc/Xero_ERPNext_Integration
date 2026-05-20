import base64
import hashlib
import hmac
import json

import frappe
from frappe import _


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep — Xero sends webhook POSTs without session auth; guest access is required by design
def webhook():
	"""Main Xero webhook endpoint"""
	try:
		request = frappe.local.request

		if request.method == "GET":
			return handle_intent_to_receive()
		elif request.method == "POST":
			return handle_webhook_event()

		frappe.local.response.http_status_code = 405
		return "Method Not Allowed"

	except Exception as e:
		# B1 fix: keyword args for frappe.log_error throughout this file
		frappe.log_error(title="Xero Webhook Handler", message=f"Xero Webhook Error: {str(e)}")
		frappe.local.response.http_status_code = 500
		return "Internal Server Error"


def handle_intent_to_receive():
	"""Handle Xero's intent to receive challenge (GET request)"""
	try:
		request = frappe.local.request

		challenge = request.args.get("challenge")
		if not challenge:
			frappe.local.response.http_status_code = 400
			return "Bad Request"

		return challenge

	except Exception as e:
		frappe.log_error(title="Xero Webhook", message=f"Error handling intent to receive: {str(e)}")
		frappe.local.response.http_status_code = 500
		return "Internal Server Error"


def handle_webhook_event():
	"""Handle actual webhook events (POST request)"""
	try:
		settings = frappe.get_single("Xero Settings")
		webhook_key = settings.get_password("webhook_secret")
		request = frappe.local.request

		provided_signature = request.headers.get("X-Xero-Signature")
		if not provided_signature:
			frappe.local.response.http_status_code = 401
			return "Unauthorized"

		hashed = hmac.new(bytes(webhook_key, "utf8"), request.data, hashlib.sha256)
		generated_signature = base64.b64encode(hashed.digest()).decode("utf-8")

		if not hmac.compare_digest(provided_signature, generated_signature):
			frappe.local.response.http_status_code = 401
			return "Unauthorized"

		try:
			req_data = request.json() if callable(request.json) else request.json
		except (ValueError, AttributeError):
			req_data = frappe.local.form_dict

		if req_data.get("events"):
			for event in req_data["events"]:
				process_webhook_event(event)

		frappe.local.response.http_status_code = 200
		return "OK"

	except Exception as e:
		frappe.log_error(title="Xero Webhook Handler", message=f"Error handling webhook event: {str(e)}")
		frappe.local.response.http_status_code = 500
		return "Internal Server Error"


def process_webhook_event(event):
	"""Process individual webhook event"""
	try:
		event_category = event.get("eventCategory")
		event_type = event.get("eventType")
		resource_id = event.get("resourceId")

		if event_category == "INVOICE" and event_type == "UPDATE":
			update_invoice_from_xero(resource_id)

	except Exception as e:
		frappe.log_error(title="Xero Webhook Event Processing", message=f"Error processing webhook event: {str(e)}")


def update_invoice_from_xero(invoice_id):
	"""Update existing invoice from Xero - handle status changes like PAID/VOIDED"""
	try:
		from .base import get_xero_client

		client = get_xero_client()
		response = client.make_request("GET", f"/Invoices/{invoice_id}")

		if not response or "Invoices" not in response:
			frappe.log_error(title="Xero Webhook", message=f"Invoice {invoice_id} not found in Xero")
			return

		xero_invoice = response["Invoices"][0]
		status = xero_invoice.get("Status")
		amount_paid = float(xero_invoice.get("AmountPaid", 0))

		# B3 fix: ignore_permissions — webhook runs in background/guest context
		sales_invoice_list = frappe.get_all(
			"Sales Invoice",
			filters={"custom_xero_invoice_number": invoice_id},
			fields=["name", "customer", "grand_total", "docstatus"],
			limit=1,
			ignore_permissions=True,
		)

		if not sales_invoice_list:
			frappe.log_error(title="Xero Webhook", message=f"No ERPNext invoice found for Xero invoice {invoice_id}")
			return

		sales_invoice = sales_invoice_list[0]

		if status == "PAID" and amount_paid > 0:
			handle_paid_invoice(sales_invoice, xero_invoice, amount_paid)
		elif status == "VOIDED":
			handle_voided_invoice(sales_invoice, invoice_id)

		frappe.logger().info(f"Xero Webhook: processed {status} invoice {invoice_id}")

	except Exception as e:
		frappe.log_error(title="Xero Webhook", message=f"Error updating invoice {invoice_id} from Xero: {str(e)}")


def handle_paid_invoice(sales_invoice, xero_invoice, amount_paid):
	"""Handle when an invoice is marked as PAID in Xero"""
	try:
		sales_invoice_doc = frappe.get_doc("Sales Invoice", sales_invoice["name"])

		xero_invoice_id = xero_invoice.get("InvoiceID")
		if xero_invoice_id:
			sales_invoice_doc.custom_xero_invoice_number = xero_invoice_id
			# B4 fix: ignore_permissions — webhook handler runs without session user
			sales_invoice_doc.save(ignore_permissions=True)

		try:
			payment_entry = frappe.new_doc("Payment Entry")
			payment_entry.payment_type = "Receive"
			payment_entry.party_type = "Customer"
			payment_entry.party = sales_invoice_doc.customer
			payment_entry.paid_amount = amount_paid
			payment_entry.received_amount = amount_paid
			# B7 fix: use frappe.db.get_value explicitly instead of frappe.get_value alias
			payment_entry.paid_from = frappe.db.get_value(
				"Company", sales_invoice_doc.company, "default_receivable_account"
			)
			payment_entry.paid_to = frappe.db.get_value(
				"Company", sales_invoice_doc.company, "default_cash_account"
			)
			payment_entry.reference_no = f"Xero-{xero_invoice_id}"
			payment_entry.reference_date = frappe.utils.today()

			payment_entry.append(
				"references",
				{
					"reference_doctype": "Sales Invoice",
					"reference_name": sales_invoice_doc.name,
					"allocated_amount": amount_paid,
				},
			)

			# B4 fix: ignore_permissions
			payment_entry.insert(ignore_permissions=True)
			payment_entry.submit()

			frappe.logger().info(
				f"Xero Webhook: created payment entry {payment_entry.name} for invoice {sales_invoice['name']}"
			)

		except Exception as payment_error:
			# C2 fix: removed 8+ frappe.log_error() debug/trace calls — use single error log on failure
			frappe.log_error(
				title="Xero Webhook Payment Error",
				message=f"Failed to create payment entry for invoice {sales_invoice['name']}: {str(payment_error)}",
			)

	except Exception as e:
		frappe.log_error(
			title="Xero Webhook Error",
			message=f"Error handling paid invoice {sales_invoice['name']}: {str(e)}",
		)


def handle_voided_invoice(sales_invoice, xero_invoice_id):
	"""Handle when an invoice is VOIDED in Xero"""
	try:
		# C2 fix: was calling sync_voided_invoices() — the full batch job that fetches ALL voided
		# invoices from Xero for today. For a single webhook event, cancel only this one invoice.
		from ..schedulers.voided_invoice_sync import cancel_invoice_in_erpnext

		cancel_invoice_in_erpnext(
			{"name": sales_invoice["name"]},
			xero_invoice_id,
			None,
		)

	except Exception as e:
		frappe.log_error(
			title="Xero Webhook",
			message=f"Error handling voided invoice {sales_invoice['name']}: {str(e)}",
		)
