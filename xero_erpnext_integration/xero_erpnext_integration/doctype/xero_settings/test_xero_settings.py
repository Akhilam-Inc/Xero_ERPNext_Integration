# Copyright (c) 2025, nasirucode and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestXeroSettingsDocType(FrappeTestCase):
	"""Verify Xero Settings DocType schema and field security."""

	def _get_field(self, fieldname):
		return next(
			(f for f in frappe.get_meta("Xero Settings").fields if f.fieldname == fieldname),
			None,
		)

	def test_access_token_is_password_field(self):
		field = self._get_field("access_token")
		self.assertIsNotNone(field, "access_token field missing from Xero Settings")
		self.assertEqual(
			field.fieldtype, "Password",
			"access_token must be Password fieldtype to prevent plaintext storage",
		)

	def test_refresh_token_is_password_field(self):
		field = self._get_field("refresh_token")
		self.assertIsNotNone(field, "refresh_token field missing from Xero Settings")
		self.assertEqual(
			field.fieldtype, "Password",
			"refresh_token must be Password fieldtype to prevent plaintext storage",
		)

	def test_client_secret_is_password_field(self):
		field = self._get_field("client_secret")
		self.assertIsNotNone(field, "client_secret field missing from Xero Settings")
		self.assertEqual(
			field.fieldtype, "Password",
			"client_secret must be Password fieldtype",
		)

	def test_xero_settings_is_single_doctype(self):
		self.assertTrue(
			frappe.get_meta("Xero Settings").issingle,
			"Xero Settings must be a Single DocType",
		)

	def test_required_fields_present(self):
		meta = frappe.get_meta("Xero Settings")
		fieldnames = [f.fieldname for f in meta.fields]
		for required in ("client_id", "client_secret", "redirect_uri", "access_token", "refresh_token", "tenant_id"):
			self.assertIn(required, fieldnames, f"Required field '{required}' missing from Xero Settings")
