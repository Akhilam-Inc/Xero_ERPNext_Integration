# Copyright (c) 2025, nasirucode and Contributors
# See license.txt

from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests.utils import FrappeTestCase

XERO_CLIENT_PATH = "xero_erpnext_integration.xero_erpnext_integration.apis.base.get_xero_client"


def _patch_sales_invoice_lookup(invoices):
	"""Patch get_all only for Sales Invoice queries so Error Log writes still work."""
	real_get_all = frappe.get_all

	def side_effect(doctype, *args, **kwargs):
		if doctype == "Sales Invoice":
			return invoices
		return real_get_all(doctype, *args, **kwargs)

	return patch("frappe.get_all", side_effect=side_effect)


# ---------------------------------------------------------------------------
# sync_voided_invoices
# ---------------------------------------------------------------------------


class TestSyncVoidedInvoices(FrappeTestCase):
	@patch(XERO_CLIENT_PATH)
	def test_returns_early_when_no_response(self, mock_factory):
		mock_client = MagicMock()
		mock_client.make_request.return_value = None
		mock_factory.return_value = mock_client

		from xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync import (
			sync_voided_invoices,
		)

		# Should not raise
		sync_voided_invoices()

	@patch(XERO_CLIENT_PATH)
	def test_processes_each_voided_invoice(self, mock_factory):
		mock_client = MagicMock()
		mock_client.make_request.return_value = {
			"Invoices": [
				{"InvoiceID": "xero-id-1", "InvoiceNumber": "INV-001"},
				{"InvoiceID": "xero-id-2", "InvoiceNumber": "INV-002"},
			]
		}
		mock_factory.return_value = mock_client

		with patch(
			"xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync.process_voided_invoice"
		) as mock_process:
			from xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync import (
				sync_voided_invoices,
			)

			sync_voided_invoices()

		self.assertEqual(mock_process.call_count, 2)

	@patch(XERO_CLIENT_PATH)
	def test_handles_empty_invoices_list(self, mock_factory):
		mock_client = MagicMock()
		mock_client.make_request.return_value = {"Invoices": []}
		mock_factory.return_value = mock_client

		with patch(
			"xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync.process_voided_invoice"
		) as mock_process:
			from xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync import (
				sync_voided_invoices,
			)

			sync_voided_invoices()

		mock_process.assert_not_called()


# ---------------------------------------------------------------------------
# process_voided_invoice
# ---------------------------------------------------------------------------


class TestProcessVoidedInvoice(FrappeTestCase):
	def test_skips_when_no_matching_erpnext_invoice(self):
		with _patch_sales_invoice_lookup([]):
			from xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync import (
				process_voided_invoice,
			)

			# Should not raise
			process_voided_invoice({"InvoiceID": "unknown-id", "InvoiceNumber": "INV-X"})

	def test_skips_already_cancelled_invoice(self):
		with (
			_patch_sales_invoice_lookup([{"name": "SINV-001", "docstatus": 2, "grand_total": 100}]),
			patch("xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync.cancel_invoice_in_erpnext") as mock_cancel,
		):
			from xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync import (
				process_voided_invoice,
			)
			process_voided_invoice({"InvoiceID": "xero-id", "InvoiceNumber": "INV-001"})

		mock_cancel.assert_not_called()

	def test_skips_draft_invoice(self):
		with (
			_patch_sales_invoice_lookup([{"name": "SINV-002", "docstatus": 0, "grand_total": 100}]),
			patch("xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync.cancel_invoice_in_erpnext") as mock_cancel,
		):
			from xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync import (
				process_voided_invoice,
			)
			process_voided_invoice({"InvoiceID": "xero-id", "InvoiceNumber": "INV-002"})

		mock_cancel.assert_not_called()

	def test_cancels_submitted_invoice(self):
		with (
			_patch_sales_invoice_lookup([{"name": "SINV-003", "docstatus": 1, "grand_total": 100}]),
			patch("xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync.cancel_invoice_in_erpnext") as mock_cancel,
		):
			from xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync import (
				process_voided_invoice,
			)
			process_voided_invoice({"InvoiceID": "xero-id", "InvoiceNumber": "INV-003"})

		mock_cancel.assert_called_once()


# ---------------------------------------------------------------------------
# cancel_invoice_in_erpnext
# ---------------------------------------------------------------------------


class TestCancelInvoiceInErpnext(FrappeTestCase):
	def test_cancels_and_adds_comment(self):
		mock_doc = MagicMock()
		mock_doc.name = "SINV-004"

		with patch("frappe.get_doc", return_value=mock_doc):
			from xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync import (
				cancel_invoice_in_erpnext,
			)

			cancel_invoice_in_erpnext({"name": "SINV-004"}, "xero-uuid", "INV-004")

		mock_doc.cancel.assert_called_once()
		mock_doc.add_comment.assert_called_once()
		comment_text = mock_doc.add_comment.call_args[0][1]
		self.assertIn("xero-uuid", comment_text)
