import json

import frappe

from .base import get_xero_client


@frappe.whitelist()
def get_xero_contacts() -> dict:
	"""Get all Xero contacts"""
	try:
		client = get_xero_client()
		response = client.make_request("GET", "/Contacts")

		return {"status": "success", "data": response.get("Contacts", [])}

	except Exception as e:
		return {"status": "error", "message": str(e)}


# A4 fix: removed dead module-level `get_contact(self, ...)` function.
# It had a `self` parameter (not a class method), called self.make_request()
# which would crash if called as a plain function, and was never invoked anywhere.
# The equivalent functionality is available via XeroAPIClient.get_payments() in base.py.


@frappe.whitelist()
def create_contact(doc: str, method: str | None = None) -> dict | None:
	"""Create contact in Xero"""
	try:
		client = get_xero_client()
		contact = frappe.get_doc("Contact", doc)

		is_customer = False
		is_supplier = False

		# B6 fix: use doc.get() instead of hasattr() — hasattr always returns True on Frappe docs
		if contact.get("links"):
			for link in contact.links:
				if link.link_doctype == "Customer":
					is_customer = True
				if link.link_doctype == "Supplier":
					is_supplier = True

		contact_data = {
			"Name": contact.name,
			"FirstName": contact.first_name or "",
			"LastName": contact.last_name or "",
			"EmailAddress": contact.email_id or "",
			"AccountNumber": contact.custom_account_number or contact.name,
			"IsCustomer": is_customer,
			"IsSupplier": is_supplier,
			"Addresses": [
				{
					"AddressType": "STREET",
					"AddressLine1": contact.address or "",
				}
			],
			"Phones": [{"PhoneType": "DEFAULT", "PhoneNumber": contact.phone or contact.mobile_no or ""}],
		}
		data = {"Contacts": [contact_data]}
		response = client.make_request("POST", "/Contacts", data=data)

		if response:
			return {"status": "success", "data": response.get("Contacts", [])}
		return None

	except Exception as e:
		frappe.log_error(title="Xero Create Contact", message=f"Failed to create contact: {e!s}")
		return None
