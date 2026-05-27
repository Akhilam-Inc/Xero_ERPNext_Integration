# Copyright (c) 2025, nasirucode and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

XERO_CLIENT_PATH = "xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry.get_xero_client"


def _make_mock_payment(payment_type="Receive", xero_invoice_id="xero-inv-id", paid_to="Cash - TC"):
	payment = MagicMock()
	payment.payment_type = payment_type
	payment.paid_amount = 500.0
	payment.posting_date = frappe.utils.getdate()
	payment.reference_no = "REF-001"
	payment.paid_to = paid_to

	ref = MagicMock()
	ref.reference_doctype = "Sales Invoice"
	ref.reference_name = "SINV-TEST"
	payment.references = [ref]

	sinv = MagicMock()
	sinv.get = lambda k: xero_invoice_id if k == "custom_xero_invoice_number" else None

	payment.get_doc_side_effects = {"Sales Invoice": sinv}
	return payment


class TestCreatePayment(FrappeTestCase):
	def test_throws_when_payment_type_is_not_receive(self):
		from xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry import create_payment

		mock_payment = _make_mock_payment(payment_type="Pay")
		self.assertRaises(frappe.ValidationError, create_payment, mock_payment)

	@patch(XERO_CLIENT_PATH)
	def test_throws_when_no_xero_invoice_id_on_reference(self, mock_factory):
		mock_factory.return_value = MagicMock()

		from xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry import create_payment

		mock_payment = _make_mock_payment(xero_invoice_id=None)

		sinv = MagicMock()
		sinv.get.return_value = None
		with patch("frappe.get_doc", return_value=sinv):
			self.assertRaises(frappe.ValidationError, create_payment, mock_payment)

	@patch(XERO_CLIENT_PATH)
	def test_successful_create_returns_payment_id(self, mock_factory):
		mock_client = MagicMock()
		mock_client.make_request.return_value = {"Payments": [{"PaymentID": "xero-pay-id-001"}]}
		mock_factory.return_value = mock_client

		mock_payment = _make_mock_payment()
		sinv = MagicMock()
		sinv.get.return_value = "xero-inv-id"

		with (
			patch("frappe.get_doc", return_value=sinv),
			patch(
				"xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry.get_account_code",
				return_value="880",
			),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry import create_payment

			result = create_payment(mock_payment)

		self.assertEqual(result["status"], "success")
		self.assertIn("xero-pay-id-001", result["message"])


class TestGetAccountCode(FrappeTestCase):
	def test_returns_default_code_880(self):
		# get_account_code uses frappe.db.get_value / frappe.db.get_single_value — not frappe.get_doc
		with (
			patch("frappe.db.get_value", return_value=None),  # no custom_xero_account_code on account
			patch(
				"frappe.db.get_single_value", return_value="880"
			),  # default_account_code from Xero Settings
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry import get_account_code

			result = get_account_code("Cash - _TC")
		self.assertEqual(result, "880")

	def test_returns_none_on_missing_account(self):
		with patch("frappe.db.get_value", side_effect=Exception("Account not found")):
			from xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry import get_account_code

			result = get_account_code("Non-Existent Account")
		self.assertIsNone(result)


class TestSyncPaymentToXero(FrappeTestCase):
	@patch(XERO_CLIENT_PATH)
	def test_delegates_to_create_payment(self, mock_factory):
		mock_client = MagicMock()
		mock_client.make_request.return_value = {"Payments": [{"PaymentID": "xero-pay-999"}]}
		mock_factory.return_value = mock_client

		mock_payment = _make_mock_payment()

		with (
			# frappe.get_doc is called exactly once (sync_payment_to_xero loads the PE doc);
			# create_payment receives the doc object directly so get_doc is not called again.
			patch("frappe.get_doc", return_value=mock_payment),
			# create_payment uses frappe.db.get_value to fetch custom_xero_invoice_number
			patch("frappe.db.get_value", return_value="xero-inv-id"),
			patch(
				"xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry.get_account_code",
				return_value="880",
			),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry import (
				sync_payment_to_xero,
			)

			result = sync_payment_to_xero("PE-FAKE-001")

		self.assertEqual(result["status"], "success")
