# Copyright (c) 2025, nasirucode and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from xero_erpnext_integration.xero_erpnext_integration.tests.utils import insert_test_customer

XERO_CLIENT_PATH = "xero_erpnext_integration.xero_erpnext_integration.apis.contact.get_xero_client"


class TestGetXeroContacts(FrappeTestCase):
	@patch(XERO_CLIENT_PATH)
	def test_returns_contacts_list_on_success(self, mock_factory):
		mock_client = MagicMock()
		mock_client.make_request.return_value = {"Contacts": [{"ContactID": "c1", "Name": "Test Corp"}]}
		mock_factory.return_value = mock_client

		from xero_erpnext_integration.xero_erpnext_integration.apis.contact import get_xero_contacts

		result = get_xero_contacts()
		self.assertEqual(result["status"], "success")
		self.assertEqual(len(result["data"]), 1)

	@patch(XERO_CLIENT_PATH)
	def test_returns_error_on_exception(self, mock_factory):
		mock_factory.side_effect = Exception("API unavailable")

		from xero_erpnext_integration.xero_erpnext_integration.apis.contact import get_xero_contacts

		result = get_xero_contacts()
		self.assertEqual(result["status"], "error")


class TestCreateContact(FrappeTestCase):
	def setUp(self):
		# Customer contact
		self.customer = insert_test_customer("_XeroTest ContactCreate")

		self.contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "_XeroTest",
				"last_name": "ContactCreate",
				"links": [{"link_doctype": "Customer", "link_name": self.customer.name}],
			}
		).insert(ignore_permissions=True)

	@patch(XERO_CLIENT_PATH)
	def test_creates_contact_with_customer_flag(self, mock_factory):
		mock_client = MagicMock()
		mock_client.make_request.return_value = {"Contacts": [{"ContactID": "new-xero-id"}]}
		mock_factory.return_value = mock_client

		from xero_erpnext_integration.xero_erpnext_integration.apis.contact import create_contact

		result = create_contact(self.contact.name)

		self.assertEqual(result["status"], "success")
		# Verify payload sent to Xero had IsCustomer=True
		call_data = mock_client.make_request.call_args[1]["data"]
		self.assertTrue(call_data["Contacts"][0]["IsCustomer"])

	@patch(XERO_CLIENT_PATH)
	def test_returns_none_when_api_fails(self, mock_factory):
		mock_factory.side_effect = Exception("Xero down")

		from xero_erpnext_integration.xero_erpnext_integration.apis.contact import create_contact

		result = create_contact(self.contact.name)
		self.assertIsNone(result)
