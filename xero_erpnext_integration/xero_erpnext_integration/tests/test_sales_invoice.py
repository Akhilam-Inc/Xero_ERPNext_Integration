# Copyright (c) 2025, nasirucode and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today
from xero_erpnext_integration.xero_erpnext_integration.tests.utils import insert_test_customer

XERO_CLIENT_PATH = "xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.get_xero_client"
MOCK_CONTACT_ID = "xero-contact-uuid-001"
MOCK_INVOICE_ID = "xero-invoice-uuid-001"


def _mock_client(make_request_return=None):
	client = MagicMock()
	client.make_request.return_value = make_request_return or {}
	return client


# ---------------------------------------------------------------------------
# get_customer_contact_id
# ---------------------------------------------------------------------------


class TestGetCustomerContactId(FrappeTestCase):
	def setUp(self):
		# Customer whose contact_id is stored directly on the Customer doc
		self.direct_customer = insert_test_customer("_XeroTest Direct")
		frappe.db.set_value("Customer", self.direct_customer.name, "custom_contact_id", MOCK_CONTACT_ID)

		# Customer whose contact_id comes through a Contact linked via Dynamic Link
		self.linked_customer = insert_test_customer("_XeroTest Linked")
		self.contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "_XeroTest",
				"links": [{"link_doctype": "Customer", "link_name": self.linked_customer.name}],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Contact", self.contact.name, "custom_contact_id", "linked-id-999")

	def test_returns_contact_id_directly_from_customer(self):
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import (
			get_customer_contact_id,
		)

		result = get_customer_contact_id(self.direct_customer.name)
		self.assertEqual(result, MOCK_CONTACT_ID)

	def test_falls_back_to_contact_dynamic_link(self):
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import (
			get_customer_contact_id,
		)

		result = get_customer_contact_id(self.linked_customer.name)
		self.assertEqual(result, "linked-id-999")

	def test_returns_none_when_no_contact_mapped(self):
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import (
			get_customer_contact_id,
		)

		orphan = insert_test_customer("_XeroTest Orphan")
		result = get_customer_contact_id(orphan.name)
		self.assertIsNone(result)


# ---------------------------------------------------------------------------
# create_invoice
# ---------------------------------------------------------------------------


class TestCreateInvoice(FrappeTestCase):
	def _make_mock_invoice(self, **overrides):
		"""Return a MagicMock that looks like a Sales Invoice doc."""
		doc = MagicMock()
		doc.name = "SINV-TEST-0001"
		doc.doctype = "Sales Invoice"
		doc.customer = "_Test Customer"
		doc.company = "_Test Company"
		doc.currency = "USD"
		doc.posting_date = frappe.utils.getdate(today())
		doc.due_date = frappe.utils.getdate(add_days(today(), 30))
		doc.custom_xero_invoice_number = None
		doc.workflow_state = "Draft"
		doc.is_return = 0
		doc.taxes = []
		item = MagicMock()
		item.description = "Test Item"
		item.item_name = "Test Item"
		item.qty = 1
		item.rate = 100
		item.get = lambda k, d=None: None
		doc.items = [item]
		for k, v in overrides.items():
			setattr(doc, k, v)
		return doc

	@patch(XERO_CLIENT_PATH)
	def test_throws_when_contact_id_missing(self, mock_factory):
		mock_factory.return_value = _mock_client()
		mock_invoice = self._make_mock_invoice()

		with (
			patch(
				"xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.get_customer_contact_id",
				return_value=None,
			),
			patch("frappe.get_doc", return_value=mock_invoice),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import create_invoice

			self.assertRaises(frappe.ValidationError, create_invoice, mock_invoice.name)

	@patch(XERO_CLIENT_PATH)
	def test_throws_when_posting_date_missing(self, mock_factory):
		mock_factory.return_value = _mock_client()
		mock_invoice = self._make_mock_invoice(posting_date=None)

		with (
			patch(
				"xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.get_customer_contact_id",
				return_value=MOCK_CONTACT_ID,
			),
			patch("frappe.get_doc", return_value=mock_invoice),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import create_invoice

			self.assertRaises(frappe.ValidationError, create_invoice, mock_invoice.name)

	@patch(XERO_CLIENT_PATH)
	def test_throws_when_due_date_missing(self, mock_factory):
		mock_factory.return_value = _mock_client()
		mock_invoice = self._make_mock_invoice(due_date=None)

		with (
			patch(
				"xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.get_customer_contact_id",
				return_value=MOCK_CONTACT_ID,
			),
			patch("frappe.get_doc", return_value=mock_invoice),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import create_invoice

			self.assertRaises(frappe.ValidationError, create_invoice, mock_invoice.name)

	@patch(XERO_CLIENT_PATH)
	def test_successful_create_returns_invoice_id(self, mock_factory):
		mock_factory.return_value = _mock_client(
			{"Invoices": [{"InvoiceID": MOCK_INVOICE_ID, "Status": "AUTHORISED"}]}
		)
		mock_invoice = self._make_mock_invoice()
		# frappe.get_single is a standalone function in Frappe v16 (does not go through
		# frappe.get_doc), so it must be patched separately with a valid settings object.
		mock_settings = MagicMock()
		mock_settings.default_account_code = "200"
		mock_settings.default_tax_type = "NONE"

		with (
			patch(
				"xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.get_customer_contact_id",
				return_value=MOCK_CONTACT_ID,
			),
			patch("frappe.get_doc", return_value=mock_invoice),
			patch("frappe.get_single", return_value=mock_settings),
			patch("frappe.get_cached_value", return_value="USD"),
			patch(
				"frappe.db.get_single_value",
				side_effect=lambda dt, field: "200" if field == "default_account_code" else None,
			),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import create_invoice

			result = create_invoice(mock_invoice.name)

		self.assertEqual(result["status"], "success")
		self.assertEqual(result["data"]["InvoiceID"], MOCK_INVOICE_ID)

	@patch(XERO_CLIENT_PATH)
	def test_updates_existing_invoice_when_synced(self, mock_factory):
		mock_client = _mock_client({"Invoices": [{"InvoiceID": MOCK_INVOICE_ID, "Status": "AUTHORISED"}]})
		mock_factory.return_value = mock_client
		mock_invoice = self._make_mock_invoice(
			custom_xero_invoice_number=MOCK_INVOICE_ID,
			workflow_state="Synced to Xero",
		)
		mock_settings = MagicMock()
		mock_settings.default_account_code = "200"
		mock_settings.default_tax_type = "NONE"

		with (
			patch(
				"xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.get_customer_contact_id",
				return_value=MOCK_CONTACT_ID,
			),
			patch("frappe.get_doc", return_value=mock_invoice),
			patch("frappe.get_single", return_value=mock_settings),
			patch("frappe.get_cached_value", return_value="USD"),
			patch(
				"frappe.db.get_single_value",
				side_effect=lambda dt, field: "200" if field == "default_account_code" else None,
			),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import create_invoice

			create_invoice(mock_invoice.name, update_invoice=True)

		# Assert PUT-style URL was used (update, not create)
		call_url = mock_client.make_request.call_args[0][1]
		self.assertIn(MOCK_INVOICE_ID, call_url)


# ---------------------------------------------------------------------------
# cancel_invoice_in_xero
# ---------------------------------------------------------------------------


class TestCancelInvoiceInXero(FrappeTestCase):
	@patch(XERO_CLIENT_PATH)
	def test_returns_info_when_already_paid(self, mock_factory):
		mock_factory.return_value = _mock_client(
			{"Invoices": [{"InvoiceID": MOCK_INVOICE_ID, "Status": "PAID"}]}
		)
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import (
			cancel_invoice_in_xero,
		)

		result = cancel_invoice_in_xero(MOCK_INVOICE_ID)
		self.assertEqual(result["status"], "info")

	@patch(XERO_CLIENT_PATH)
	def test_returns_info_when_already_voided(self, mock_factory):
		mock_factory.return_value = _mock_client(
			{"Invoices": [{"InvoiceID": MOCK_INVOICE_ID, "Status": "VOIDED"}]}
		)
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import (
			cancel_invoice_in_xero,
		)

		result = cancel_invoice_in_xero(MOCK_INVOICE_ID)
		self.assertEqual(result["status"], "info")

	@patch(XERO_CLIENT_PATH)
	def test_voids_authorised_invoice_successfully(self, mock_factory):
		mock_client = MagicMock()
		mock_client.make_request.side_effect = [
			{"Invoices": [{"InvoiceID": MOCK_INVOICE_ID, "Status": "AUTHORISED"}]},
			{"Invoices": [{"InvoiceID": MOCK_INVOICE_ID, "Status": "VOIDED"}]},
		]
		mock_factory.return_value = mock_client
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import (
			cancel_invoice_in_xero,
		)

		result = cancel_invoice_in_xero(MOCK_INVOICE_ID)
		self.assertEqual(result["status"], "success")

	@patch(XERO_CLIENT_PATH)
	def test_returns_error_when_invoice_not_found(self, mock_factory):
		mock_factory.return_value = _mock_client({})
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import (
			cancel_invoice_in_xero,
		)

		result = cancel_invoice_in_xero(MOCK_INVOICE_ID)
		self.assertEqual(result["status"], "error")


# ---------------------------------------------------------------------------
# fetch_xero_contacts
# ---------------------------------------------------------------------------


class TestFetchXeroContacts(FrappeTestCase):
	def setUp(self):
		self.contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "John",
				"last_name": "Smith",
			}
		).insert(ignore_permissions=True)

	@patch(XERO_CLIENT_PATH)
	def test_returns_matching_contacts(self, mock_factory):
		mock_factory.return_value = _mock_client(
			{
				"Contacts": [
					{"ContactID": "c1", "Name": "John Smith", "EmailAddress": "john@test.com", "Phones": []},
					{"ContactID": "c2", "Name": "Completely Different", "EmailAddress": "", "Phones": []},
				]
			}
		)
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import fetch_xero_contacts

		results = fetch_xero_contacts(self.contact.name)
		contact_ids = [c["ContactID"] for c in results]
		self.assertIn("c1", contact_ids)
		self.assertNotIn("c2", contact_ids)

	@patch(XERO_CLIENT_PATH)
	def test_returns_empty_list_when_no_matches(self, mock_factory):
		mock_factory.return_value = _mock_client(
			{"Contacts": [{"ContactID": "c9", "Name": "ZZZZZ Nobody", "EmailAddress": "", "Phones": []}]}
		)
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import fetch_xero_contacts

		results = fetch_xero_contacts(self.contact.name)
		self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# map_contact_to_xero
# ---------------------------------------------------------------------------


class TestMapContactToXero(FrappeTestCase):
	def setUp(self):
		self.customer = insert_test_customer("_XeroTest MapContact")
		self.contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "_XeroTest",
				"links": [{"link_doctype": "Customer", "link_name": self.customer.name}],
			}
		).insert(ignore_permissions=True)

	def test_sets_contact_id_on_contact_doc(self):
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import map_contact_to_xero

		with patch("frappe.get_doc") as mock_get_doc:
			mock_contact = MagicMock()
			mock_sinv = MagicMock()
			# Accept *args/**kwargs so Frappe v16 internal calls with keyword args don't crash
			mock_get_doc.side_effect = lambda *args, **kwargs: (
				mock_contact if (args[0] if args else kwargs.get("doctype")) == "Contact" else mock_sinv
			)
			result = map_contact_to_xero("contact-xero-id", self.contact.name, "SINV-FAKE")

		self.assertTrue(result)
		self.assertEqual(mock_contact.custom_contact_id, "contact-xero-id")
		self.assertEqual(mock_contact.custom_send_to_xero, 1)
		mock_contact.save.assert_called_once()

	def test_returns_false_on_exception(self):
		from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import map_contact_to_xero

		# Patch frappe.log_error too: if get_doc raises, log_error (called in the except
		# handler) would also try to insert an Error Log via get_doc and cascade-fail.
		with (
			patch("frappe.get_doc", side_effect=Exception("DB error")),
			patch("frappe.log_error"),
		):
			result = map_contact_to_xero("id", "bad-contact", "SINV-FAKE")

		self.assertFalse(result)


# ---------------------------------------------------------------------------
# sync_invoice_payments
# ---------------------------------------------------------------------------


class TestSyncInvoicePayments(FrappeTestCase):
	@patch(XERO_CLIENT_PATH)
	def test_returns_success_when_no_invoices(self, mock_factory):
		mock_factory.return_value = _mock_client()
		with patch("frappe.get_all", return_value=[]):
			from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import (
				sync_invoice_payments,
			)

			result = sync_invoice_payments()
		self.assertEqual(result["status"], "success")
		self.assertIn("No unpaid", result["message"])

	@patch(XERO_CLIENT_PATH)
	def test_processes_paid_invoices_from_xero(self, mock_factory):
		# frappe.get_all returns frappe._dict objects; plain dicts don't support attribute access
		fake_invoices = [
			frappe._dict(
				{
					"name": "SINV-0001",
					"customer": "_Test Customer",
					"grand_total": 500,
					"outstanding_amount": 500,
					"custom_xero_invoice_number": MOCK_INVOICE_ID,
					"company": "_Test Company",
				}
			)
		]
		mock_client = _mock_client(
			{
				"Invoices": [
					{
						"InvoiceID": MOCK_INVOICE_ID,
						"Status": "PAID",
						"AmountPaid": 500,
					}
				]
			}
		)
		mock_factory.return_value = mock_client

		with (
			patch("frappe.get_all", return_value=fake_invoices),
			patch(
				"xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.create_payment_entry_from_xero",
				return_value={"status": "success"},
			),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import (
				sync_invoice_payments,
			)

			result = sync_invoice_payments()

		self.assertEqual(result["status"], "success")
		self.assertEqual(len(result["data"]), 1)
		self.assertEqual(result["data"][0]["invoice"], "SINV-0001")

	@patch(XERO_CLIENT_PATH)
	def test_skips_invoices_not_in_xero_response(self, mock_factory):
		fake_invoices = [
			frappe._dict(
				{
					"name": "SINV-0002",
					"customer": "_Test Customer",
					"grand_total": 200,
					"outstanding_amount": 200,
					"custom_xero_invoice_number": "different-id",
					"company": "_Test Company",
				}
			)
		]
		mock_factory.return_value = _mock_client(
			{"Invoices": [{"InvoiceID": MOCK_INVOICE_ID, "Status": "PAID", "AmountPaid": 200}]}
		)

		with patch("frappe.get_all", return_value=fake_invoices):
			from xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice import (
				sync_invoice_payments,
			)

			result = sync_invoice_payments()

		self.assertEqual(result["status"], "success")
		self.assertEqual(len(result["data"]), 0)
