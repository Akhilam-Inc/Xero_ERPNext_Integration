# Copyright (c) 2025, nasirucode and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

XERO_CLIENT_PATH = "xero_erpnext_integration.xero_erpnext_integration.apis.connection.get_xero_client"


class TestAuthorize(FrappeTestCase):
	def test_returns_error_when_code_missing(self):
		mock_settings = MagicMock()
		mock_settings.code = None
		mock_settings.client_id = "id"
		mock_settings.get_password.return_value = "secret"

		with patch("frappe.get_single", return_value=mock_settings):
			from xero_erpnext_integration.xero_erpnext_integration.apis.connection import authorize

			result = authorize()

		self.assertEqual(result["status"], "error")
		self.assertIn("Authorization code", result["message"])

	def test_returns_error_when_client_id_missing(self):
		mock_settings = MagicMock()
		mock_settings.code = "auth-code"
		mock_settings.client_id = None
		mock_settings.get_password.return_value = None

		with patch("frappe.get_single", return_value=mock_settings):
			from xero_erpnext_integration.xero_erpnext_integration.apis.connection import authorize

			result = authorize()

		self.assertEqual(result["status"], "error")
		self.assertIn("Client ID", result["message"])

	@patch(XERO_CLIENT_PATH)
	def test_returns_success_when_exchange_succeeds(self, mock_factory):
		mock_settings = MagicMock()
		mock_settings.code = "valid-auth-code"
		mock_settings.client_id = "client-id"
		mock_settings.get_password.return_value = "client-secret"

		mock_client = MagicMock()
		mock_client.exchange_code_for_token.return_value = {
			"status": "success",
			"access_token": "new-access-token",
			"tenant_id": "tenant-123",
			"tenant_name": "Test Org",
		}
		mock_factory.return_value = mock_client

		with patch("frappe.get_single", return_value=mock_settings):
			from xero_erpnext_integration.xero_erpnext_integration.apis.connection import authorize

			result = authorize()

		self.assertEqual(result["status"], "success")

	@patch(XERO_CLIENT_PATH)
	def test_returns_friendly_message_for_invalid_grant(self, mock_factory):
		mock_settings = MagicMock()
		mock_settings.code = "expired-code"
		mock_settings.client_id = "client-id"
		mock_settings.get_password.return_value = "client-secret"

		mock_factory.return_value = MagicMock()

		with patch("frappe.get_single", return_value=mock_settings), patch(XERO_CLIENT_PATH) as mock_factory2:
			mock_factory2.return_value = MagicMock()
			mock_factory2.return_value.exchange_code_for_token.side_effect = Exception("invalid_grant")

			from xero_erpnext_integration.xero_erpnext_integration.apis.connection import authorize

			result = authorize()

		self.assertEqual(result["status"], "error")
		self.assertIn("expired", result["message"].lower())
