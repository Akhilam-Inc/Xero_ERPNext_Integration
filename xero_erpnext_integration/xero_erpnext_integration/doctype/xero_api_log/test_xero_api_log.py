# Copyright (c) 2025, nasirucode and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestXeroAPILog(FrappeTestCase):
	"""Verify Xero API Log DocType schema and naming rule."""

	def test_naming_rule_is_expression_not_old_style(self):
		naming_rule = frappe.db.get_value("DocType", "Xero API Log", "naming_rule")
		self.assertEqual(
			naming_rule, "Expression",
			"naming_rule must be 'Expression', not 'Expression (old style)' — old style is removed in v16",
		)

	def test_autoname_pattern_is_set(self):
		autoname = frappe.db.get_value("DocType", "Xero API Log", "autoname")
		self.assertTrue(autoname, "autoname expression must be set for Xero API Log")
		self.assertIn("XR", autoname, "autoname should use XR prefix")

	def test_can_create_log_entry(self):
		log = frappe.get_doc({
			"doctype": "Xero API Log",
			"api_method": "GET",
			"api_url": "https://api.xero.com/api.xro/2.0/Invoices",
			"message": "Success",
			"status_code": "200",
			"timestamp": frappe.utils.now_datetime(),
		}).insert(ignore_permissions=True)

		self.assertTrue(log.name.startswith("XR"), f"Log name '{log.name}' should start with XR")

	def test_log_has_required_fields(self):
		meta = frappe.get_meta("Xero API Log")
		fieldnames = [f.fieldname for f in meta.fields]
		for required in ("api_method", "api_url", "message", "status_code", "payload", "response"):
			self.assertIn(required, fieldnames, f"Field '{required}' missing from Xero API Log")
