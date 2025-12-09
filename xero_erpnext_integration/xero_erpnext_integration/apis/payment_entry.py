import json

import frappe

from .base import get_xero_client


@frappe.whitelist()
def create_payment(doc, method=None):
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
			frappe.throw("Only 'Receive' payment entries can be synced to Xero")

		# Get the related invoice's Xero ID
		invoice_xero_id = None
		if payment.references:
			for ref in payment.references:
				if ref.reference_doctype == "Sales Invoice":
					# Get Xero Invoice ID from the Sales Invoice
					sales_invoice = frappe.get_doc("Sales Invoice", ref.reference_name)
					invoice_xero_id = sales_invoice.get("custom_xero_invoice_number")
					break

		if not invoice_xero_id:
			frappe.throw("No Xero Invoice ID found in the referenced Sales Invoice")

		# Get account code from the payment account
		account_code = get_account_code(payment.paid_to)
		if not account_code:
			frappe.throw(f"No account code found for account: {payment.paid_to}")

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
		frappe.log_error("Xero Create Payment", f"Failed to create payment in Xero: {str(e)}")
		frappe.throw(f"Failed to create payment in Xero: {str(e)}")
		return False


@frappe.whitelist()
def get_account_code(account_name):
	"""Get account code for the given account"""
	try:
		account = frappe.get_doc("Account", account_name)

		# if account.get("account_number"):
		#     return account.account_number

		# Default fallback
		return "880"  # Default bank account code

	except Exception as e:
		frappe.log_error("Get Account Code", f"Error getting account code for {account_name}: {str(e)}")
		return None


@frappe.whitelist()
def get_customer_contact_id(customer):
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
			"Get Customer Contact ID", f"Error getting contact id for customer {customer}: {str(e)}"
		)
		return None


@frappe.whitelist()
def sync_payment_to_xero(payment_entry_name):
	"""Manual sync function to create payment in Xero"""
	try:
		payment_entry = frappe.get_doc("Payment Entry", payment_entry_name)
		result = create_payment(payment_entry)
		return result
	except Exception as e:
		frappe.throw(f"Failed to sync payment to Xero: {str(e)}")
