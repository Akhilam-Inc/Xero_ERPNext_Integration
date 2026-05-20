import frappe


@frappe.whitelist()
def create_payment_from_xero(xero_invoice_id: str, payment_amount: float) -> dict:
	"""Create payment entry when payment is received in Xero"""
	try:
		# A1 fix: correct filter field — was "xero_invoice_id" (non-existent)
		sales_invoice_name = frappe.db.get_value(
			"Sales Invoice", {"custom_xero_invoice_number": xero_invoice_id}, "name"
		)

		if not sales_invoice_name:
			return {"status": "error", "message": f"No ERPNext invoice found for Xero ID: {xero_invoice_id}"}

		sales_invoice = frappe.get_doc("Sales Invoice", sales_invoice_name)

		if sales_invoice.status == "Paid":
			return {"status": "info", "message": f"Invoice {sales_invoice_name} already marked as paid"}

		payment_entry = frappe.get_doc(
			{
				"doctype": "Payment Entry",
				"payment_type": "Receive",
				"party_type": "Customer",
				"party": sales_invoice.customer,
				"paid_amount": payment_amount,
				"received_amount": payment_amount,
				"target_exchange_rate": 1,
				"reference_no": f"Xero-{xero_invoice_id}",
				"reference_date": frappe.utils.today(),
				"paid_to": get_default_receivable_account(sales_invoice.company),
				"paid_from": get_default_cash_account(sales_invoice.company),
				"references": [
					{
						"reference_doctype": "Sales Invoice",
						"reference_name": sales_invoice_name,
						"allocated_amount": payment_amount,
					}
				],
			}
		)

		payment_entry.insert(ignore_permissions=True)
		payment_entry.submit()

		return {
			"status": "success",
			"message": f"Payment entry created: {payment_entry.name}",
			"payment_entry": payment_entry.name,
		}

	except Exception as e:
		# A3 fix: use frappe.log_error (creates DB Error Log record) not frappe.logger().error
		frappe.log_error(title="Xero Payment from Xero", message=f"Failed to create payment for Xero invoice {xero_invoice_id}: {str(e)}")
		return {"status": "error", "message": str(e)}


def get_default_receivable_account(company=None):
	"""Get default receivable account"""
	# B2 fix: frappe.defaults.get_user_default returns None in background workers.
	# Pass company from the calling doc, or fall back to ERPNext global default.
	if not company:
		company = frappe.db.get_single_value("Global Defaults", "default_company")
	return frappe.db.get_value("Company", company, "default_receivable_account")


def get_default_cash_account(company=None):
	"""Get default cash account"""
	if not company:
		company = frappe.db.get_single_value("Global Defaults", "default_company")
	return frappe.db.get_value("Company", company, "default_cash_account")
