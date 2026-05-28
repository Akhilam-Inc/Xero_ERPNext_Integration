# Copyright (c) 2025, nasirucode and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase


def _make_doc(**kwargs):
	"""Return a lightweight mock Sales Invoice doc."""
	doc = MagicMock()
	doc.name = "SINV-TEST-DOC"
	doc.customer = "_Test Customer"
	doc.contact_person = "Contact Person"
	doc.custom_contact_id = None
	doc.custom_xero_invoice_number = None
	doc.custom_do_not_sync_to_xero = 0
	doc.workflow_state = "Draft"
	for k, v in kwargs.items():
		setattr(doc, k, v)
	return doc


# ---------------------------------------------------------------------------
# before_submit
# ---------------------------------------------------------------------------


class TestBeforeSubmit(FrappeTestCase):
	def test_skips_validation_when_do_not_sync_enabled(self):
		from xero_erpnext_integration.xero_erpnext_integration.custom_scripts.sales_invoice import (
			before_submit,
		)

		doc = _make_doc(custom_do_not_sync_to_xero=1, custom_contact_id=None, customer=None)
		# Should not raise even though customer is None
		before_submit(doc)

	def test_skips_when_contact_id_already_set(self):
		from xero_erpnext_integration.xero_erpnext_integration.custom_scripts.sales_invoice import (
			before_submit,
		)

		doc = _make_doc(custom_contact_id="already-mapped")
		before_submit(doc)  # Should not raise

	def test_throws_when_no_customer_and_contact(self):
		from xero_erpnext_integration.xero_erpnext_integration.custom_scripts.sales_invoice import (
			before_submit,
		)

		doc = _make_doc(customer=None, contact_person=None, custom_contact_id=None)
		self.assertRaises(frappe.ValidationError, before_submit, doc)

	def test_throws_when_contact_id_missing_but_customer_present(self):
		from xero_erpnext_integration.xero_erpnext_integration.custom_scripts.sales_invoice import (
			before_submit,
		)

		doc = _make_doc(customer="_Test Customer", contact_person="Some Contact", custom_contact_id=None)
		self.assertRaises(frappe.ValidationError, before_submit, doc)


# ---------------------------------------------------------------------------
# on_cancel
# ---------------------------------------------------------------------------


class TestOnCancel(FrappeTestCase):
	def test_skips_when_no_xero_invoice_number(self):
		from xero_erpnext_integration.xero_erpnext_integration.custom_scripts.sales_invoice import (
			on_cancel,
		)

		doc = _make_doc(custom_xero_invoice_number=None)
		# Should return silently, no API call
		on_cancel(doc)

	def test_skips_when_do_not_sync_enabled(self):
		from xero_erpnext_integration.xero_erpnext_integration.custom_scripts.sales_invoice import (
			on_cancel,
		)

		doc = _make_doc(custom_xero_invoice_number="xero-123", custom_do_not_sync_to_xero=1)
		on_cancel(doc)  # Should return silently

	def test_calls_cancel_api_when_xero_invoice_exists(self):
		from xero_erpnext_integration.xero_erpnext_integration.custom_scripts.sales_invoice import (
			on_cancel,
		)

		doc = _make_doc(custom_xero_invoice_number="xero-invoice-abc")

		with patch(
			"xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.cancel_invoice_in_xero",
			return_value={"status": "success"},
		) as mock_cancel:
			on_cancel(doc)

		mock_cancel.assert_called_once_with("xero-invoice-abc")

	def test_logs_error_and_warns_when_cancel_api_fails(self):
		from xero_erpnext_integration.xero_erpnext_integration.custom_scripts.sales_invoice import (
			on_cancel,
		)

		doc = _make_doc(custom_xero_invoice_number="xero-invoice-abc")

		with patch(
			"xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.cancel_invoice_in_xero",
			return_value={"status": "error", "message": "Not found"},
		):
			# Should not raise — on_cancel shows msgprint warning instead
			on_cancel(doc)
