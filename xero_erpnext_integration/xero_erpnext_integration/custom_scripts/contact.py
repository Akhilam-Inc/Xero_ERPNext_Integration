import frappe
from frappe import _


@frappe.whitelist()
def send_contact_to_xero(doc_name):
	"""
	Trigger Xero contact creation when button is clicked
	and the contact wasn't previously sent to Xero
	"""

	doc = frappe.get_doc("Contact", doc_name)
	# Check if custom_send_to_xero is checked and contact_id is not set
	# This ensures we only create contact once when checkbox is first checked
	if not doc.get("custom_contact_id"):
		try:
			# Call the Xero API to create contact
			from xero_erpnext_integration.xero_erpnext_integration.apis.contact import create_contact

			result = create_contact(doc.name)

			if result and result.get("status") == "success":
				# Update the document with Xero contact ID
				frappe.db.set_value("Contact", doc.name, "custom_contact_id", result["data"][0]["ContactID"])

				# Reload the document to reflect the changes
				doc.reload()

				frappe.msgprint(
					_("Contact created successfully in Xero"), title=_("Success"), indicator="green"
				)
				return True
			else:
				# Reset the checkbox if creation failed
				doc.reload()
				frappe.throw(_("Error creating contact in Xero"))

		except Exception as e:
			# Reset the checkbox if there's an error
			frappe.log_error(f"Xero Contact Creation Error: {str(e)}")
			frappe.throw(_("Error creating contact in Xero: {0}").format(str(e)))
