import frappe


def push_sales_returns():
	"""Cron entry: push ERPNext Sales Returns to Xero as Credit Notes."""
	from xero_erpnext_integration.xero_erpnext_integration.apis.credit_note import push_pending_sales_returns

	try:
		return push_pending_sales_returns()
	except Exception as e:
		frappe.log_error("Xero Credit Note Push Scheduler", str(e))
		raise


def pull_credit_notes():
	"""Cron entry: pull Xero Credit Notes into ERPNext as Sales Returns."""
	from xero_erpnext_integration.xero_erpnext_integration.apis.credit_note import pull_updated_credit_notes

	try:
		return pull_updated_credit_notes()
	except Exception as e:
		frappe.log_error("Xero Credit Note Pull Scheduler", str(e))
		raise

