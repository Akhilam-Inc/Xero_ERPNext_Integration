# Copyright (c) 2025, nasirucode and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCustomFieldFixtures(FrappeTestCase):
	"""Verify all custom fields are deployed by bench migrate."""

	def test_payment_entry_xero_payment_id(self):
		self.assertTrue(
			frappe.db.exists("Custom Field", "Payment Entry-custom_xero_payment_id"),
			"custom_xero_payment_id missing on Payment Entry",
		)

	def test_sales_invoice_xero_invoice_number(self):
		self.assertTrue(
			frappe.db.exists("Custom Field", "Sales Invoice-custom_xero_invoice_number"),
			"custom_xero_invoice_number missing on Sales Invoice",
		)

	def test_sales_invoice_do_not_sync(self):
		self.assertTrue(
			frappe.db.exists("Custom Field", "Sales Invoice-custom_do_not_sync_to_xero"),
			"custom_do_not_sync_to_xero missing on Sales Invoice",
		)

	def test_sales_invoice_contact_id(self):
		self.assertTrue(
			frappe.db.exists("Custom Field", "Sales Invoice-custom_contact_id"),
			"custom_contact_id missing on Sales Invoice",
		)

	def test_contact_send_to_xero(self):
		self.assertTrue(
			frappe.db.exists("Custom Field", "Contact-custom_send_to_xero"),
			"custom_send_to_xero missing on Contact",
		)

	def test_contact_account_number(self):
		self.assertTrue(
			frappe.db.exists("Custom Field", "Contact-custom_account_number"),
			"custom_account_number missing on Contact",
		)

	def test_contact_contact_id(self):
		self.assertTrue(
			frappe.db.exists("Custom Field", "Contact-custom_contact_id"),
			"custom_contact_id missing on Contact",
		)

	def test_customer_contact_id(self):
		self.assertTrue(
			frappe.db.exists("Custom Field", "Customer-custom_contact_id"),
			"custom_contact_id missing on Customer",
		)

	def test_xero_invoice_number_allow_on_submit(self):
		allow_on_submit = frappe.db.get_value(
			"Custom Field", "Sales Invoice-custom_xero_invoice_number", "allow_on_submit"
		)
		self.assertEqual(allow_on_submit, 1, "custom_xero_invoice_number must allow_on_submit=1")

	def test_do_not_sync_allow_on_submit(self):
		allow_on_submit = frappe.db.get_value(
			"Custom Field", "Sales Invoice-custom_do_not_sync_to_xero", "allow_on_submit"
		)
		self.assertEqual(allow_on_submit, 1, "custom_do_not_sync_to_xero must allow_on_submit=1")

	def test_customer_contact_id_is_read_only(self):
		read_only = frappe.db.get_value("Custom Field", "Customer-custom_contact_id", "read_only")
		self.assertEqual(read_only, 1, "Customer-custom_contact_id should be read_only")


class TestWorkflowFixtures(FrappeTestCase):
	"""Verify Sales Invoice workflow is deployed."""

	def test_workflow_exists(self):
		self.assertTrue(
			frappe.db.exists("Workflow", "Sales Invoice Sync to Xero"),
			"Workflow 'Sales Invoice Sync to Xero' not found",
		)

	def test_workflow_targets_sales_invoice(self):
		doc_type = frappe.db.get_value("Workflow", "Sales Invoice Sync to Xero", "document_type")
		self.assertEqual(doc_type, "Sales Invoice")

	def test_workflow_has_draft_state(self):
		states = frappe.get_all(
			"Workflow Document State",
			filters={"parent": "Sales Invoice Sync to Xero"},
			pluck="state",
		)
		self.assertIn("Draft", states)

	def test_workflow_has_synced_to_xero_state(self):
		states = frappe.get_all(
			"Workflow Document State",
			filters={"parent": "Sales Invoice Sync to Xero"},
			pluck="state",
		)
		self.assertIn("Synced to Xero", states)

	def test_workflow_has_submitted_state(self):
		states = frappe.get_all(
			"Workflow Document State",
			filters={"parent": "Sales Invoice Sync to Xero"},
			pluck="state",
		)
		self.assertIn("Submitted", states)

	def test_sync_to_xero_action_master_exists(self):
		self.assertTrue(
			frappe.db.exists("Workflow Action Master", "Sync to Xero"),
			"Workflow Action Master 'Sync to Xero' not found",
		)

	def test_workflow_has_transitions(self):
		transitions = frappe.get_all(
			"Workflow Transition",
			filters={"parent": "Sales Invoice Sync to Xero"},
		)
		self.assertGreater(len(transitions), 0, "Workflow has no transitions")
