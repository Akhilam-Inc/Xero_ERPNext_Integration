import json

import frappe
from frappe import _

from .base import get_xero_client


@frappe.whitelist()
def create_payment(doc: str, method: str | None = None):
	"""Create payment in Xero"""
	try:
		client = get_xero_client()

		# Get the Payment Entry document
		if isinstance(doc, str):
			payment = frappe.get_doc("Payment Entry", doc)
		else:
			payment = doc

		# Validate payment type - should be Receive for customer payments
		if payment.payment_type != "Receive":
			frappe.throw(_("Only 'Receive' payment entries can be synced to Xero"))

		# Get the related invoice's Xero ID
		# S3 fix: use db.get_value instead of get_doc inside loop — only one field needed
		invoice_xero_id = None
		if payment.references:
			for ref in payment.references:
				if ref.reference_doctype == "Sales Invoice":
					invoice_xero_id = frappe.db.get_value(  # nosemgrep — loop exits via break on first match; only one DB call is ever made
						"Sales Invoice", ref.reference_name, "custom_xero_invoice_number"
					)
					break

		if not invoice_xero_id:
			frappe.throw(_("No Xero Invoice ID found in the referenced Sales Invoice"))

		# Get account code from the payment account
		account_code = get_account_code(payment.paid_to)
		if not account_code:
			frappe.throw(_("No account code found for account: {0}").format(payment.paid_to))

		# Prepare payment data
		payment_data = {
			"Invoice": {"InvoiceID": invoice_xero_id},
			"Account": {"Code": account_code},
			"Date": payment.posting_date.strftime("%Y-%m-%d") if payment.posting_date else None,
			"Amount": float(payment.paid_amount),
		}

		# Add reference if available
		if payment.reference_no:
			payment_data["Reference"] = payment.reference_no

		data = {"Payments": [payment_data]}
		response = client.make_request("POST", "/Payments", data=data)

		if response and "Payments" in response:
			xero_payment = response["Payments"][0]

			return {
				"status": "success",
				"data": xero_payment,
				"message": f"Payment created in Xero with ID: {xero_payment.get('PaymentID')}",
			}

		return {"status": "error", "message": "Failed to create payment in Xero"}

	except Exception as e:
		frappe.log_error(title="Xero Create Payment", message=f"Failed to create payment in Xero: {e!s}")
		frappe.throw(_("Failed to create payment in Xero: {0}").format(str(e)))
		return False


@frappe.whitelist()
def get_account_code(account_name: str) -> str | None:
	"""Return the Xero account code for the given ERPNext bank/cash account.

	Resolution order:
	  1. custom_xero_account_code field on the Account (if set)
	  2. default_account_code from Xero Settings
	  3. None — caller will throw a user-facing error
	"""
	try:
		custom_code = frappe.db.get_value("Account", account_name, "custom_xero_account_code")
		if custom_code:
			return custom_code
		return frappe.db.get_single_value("Xero Settings", "default_account_code") or None
	except Exception as e:
		frappe.log_error(
			title="Get Account Code", message=f"Error getting account code for {account_name}: {e!s}"
		)
		return None


@frappe.whitelist()
def get_customer_contact_id(customer: str) -> str | None:
	"""Get Xero contact ID for customer"""
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
		frappe.log_error(
			title="Get Customer Contact ID",
			message=f"Error getting contact id for customer {customer}: {e!s}",
		)
		return None


@frappe.whitelist()
def sync_payment_to_xero(payment_entry_name: str):
	"""Manual sync function to create payment in Xero"""
	try:
		payment_entry = frappe.get_doc("Payment Entry", payment_entry_name)
		result = create_payment(payment_entry)
		return result
	except Exception as e:
		frappe.throw(_("Failed to sync payment to Xero: {0}").format(str(e)))
