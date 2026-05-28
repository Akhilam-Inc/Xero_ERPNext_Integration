import frappe


def insert_test_customer(customer_name, **overrides):
	"""Insert a Customer for tests without requiring ERPNext master data on CI."""
	data = {
		"doctype": "Customer",
		"customer_name": customer_name,
		"customer_type": "Individual",
		"customer_group": "All Customer Groups",
		"territory": "All Territories",
	}
	data.update(overrides)
	return frappe.get_doc(data).insert(ignore_permissions=True, ignore_links=True)
