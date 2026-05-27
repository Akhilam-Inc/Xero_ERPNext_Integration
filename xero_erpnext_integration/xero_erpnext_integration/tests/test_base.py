# Copyright (c) 2025, nasirucode and Contributors
# See license.txt

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

SETTINGS_PATH = "xero_erpnext_integration.xero_erpnext_integration.apis.base.frappe.get_single"
REQUESTS_POST = "xero_erpnext_integration.xero_erpnext_integration.apis.base.requests.post"
REQUESTS_GET = "xero_erpnext_integration.xero_erpnext_integration.apis.base.requests.get"


def _mock_settings(**overrides):
	settings = MagicMock()
	settings.client_id = "test-client-id"
	settings.get_password.return_value = "test-client-secret"
	settings.redirect_uri = "https://example.com/callback"
	settings.access_token = "test-access-token"
	settings.refresh_token = "test-refresh-token"
	settings.tenant_id = "test-tenant-id"
	settings.tenant_name = "Test Org"
	settings.token_expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
	settings.debug_mode = False
	settings.enable = True
	for k, v in overrides.items():
		setattr(settings, k, v)
	return settings


# ---------------------------------------------------------------------------
# XeroAPIClient.refresh_access_token
# ---------------------------------------------------------------------------


class TestRefreshAccessToken(FrappeTestCase):
	def test_returns_true_on_successful_refresh(self):
		mock_settings = _mock_settings()
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {
			"access_token": "new-access-token",
			"refresh_token": "new-refresh-token",
			"expires_in": 1800,
		}

		with (
			patch(SETTINGS_PATH, return_value=mock_settings),
			patch(REQUESTS_POST, return_value=mock_response),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.base import XeroAPIClient

			client = XeroAPIClient()
			result = client.refresh_access_token()

		self.assertTrue(result)
		self.assertEqual(mock_settings.access_token, "new-access-token")

	def test_returns_false_when_refresh_fails(self):
		mock_settings = _mock_settings()
		mock_response = MagicMock()
		mock_response.status_code = 401
		mock_response.text = "Unauthorized"

		with (
			patch(SETTINGS_PATH, return_value=mock_settings),
			patch(REQUESTS_POST, return_value=mock_response),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.base import XeroAPIClient

			client = XeroAPIClient()
			result = client.refresh_access_token()

		self.assertFalse(result)

	def test_returns_false_when_no_refresh_token(self):
		mock_settings = _mock_settings(refresh_token=None)

		with patch(SETTINGS_PATH, return_value=mock_settings):
			from xero_erpnext_integration.xero_erpnext_integration.apis.base import XeroAPIClient

			client = XeroAPIClient()
			client.refresh_token = None
			result = client.refresh_access_token()

		self.assertFalse(result)


# ---------------------------------------------------------------------------
# XeroAPIClient._ensure_valid_token
# ---------------------------------------------------------------------------


class TestEnsureValidToken(FrappeTestCase):
	def test_throws_when_no_access_token(self):
		mock_settings = _mock_settings(access_token=None)

		with patch(SETTINGS_PATH, return_value=mock_settings):
			from xero_erpnext_integration.xero_erpnext_integration.apis.base import XeroAPIClient

			client = XeroAPIClient()
			client.access_token = None
			self.assertRaises(frappe.ValidationError, client._ensure_valid_token)

	def test_refreshes_when_token_expired(self):
		expired_time = (datetime.now() - timedelta(minutes=1)).isoformat()
		mock_settings = _mock_settings(token_expires_at=expired_time)

		with (
			patch(SETTINGS_PATH, return_value=mock_settings),
			patch.object(
				__import__(
					"xero_erpnext_integration.xero_erpnext_integration.apis.base",
					fromlist=["XeroAPIClient"],
				).XeroAPIClient,
				"refresh_access_token",
				return_value=True,
			) as mock_refresh,
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.base import XeroAPIClient

			client = XeroAPIClient()
			client.settings.token_expires_at = expired_time
			client._ensure_valid_token()

		mock_refresh.assert_called_once()


# ---------------------------------------------------------------------------
# XeroAPIClient.make_request
# ---------------------------------------------------------------------------


class TestMakeRequest(FrappeTestCase):
	def test_successful_get_returns_parsed_json(self):
		mock_settings = _mock_settings()
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"Invoices": []}

		with (
			patch(SETTINGS_PATH, return_value=mock_settings),
			patch(REQUESTS_GET, return_value=mock_response),
			patch(
				"xero_erpnext_integration.xero_erpnext_integration.apis.base.XeroAPIClient._ensure_valid_token"
			),
			patch("xero_erpnext_integration.xero_erpnext_integration.apis.base.XeroAPIClient._log_request"),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.base import XeroAPIClient

			client = XeroAPIClient()
			result = client.make_request("GET", "/Invoices")

		self.assertEqual(result, {"Invoices": []})

	def test_401_retries_after_token_refresh(self):
		mock_settings = _mock_settings()

		first_response = MagicMock()
		first_response.status_code = 401
		first_response.text = "Unauthorized"

		second_response = MagicMock()
		second_response.status_code = 200
		second_response.json.return_value = {"Contacts": []}

		with (
			patch(SETTINGS_PATH, return_value=mock_settings),
			patch(REQUESTS_GET, side_effect=[first_response, second_response]),
			patch(
				"xero_erpnext_integration.xero_erpnext_integration.apis.base.XeroAPIClient._ensure_valid_token"
			),
			patch("xero_erpnext_integration.xero_erpnext_integration.apis.base.XeroAPIClient._log_request"),
			patch(
				"xero_erpnext_integration.xero_erpnext_integration.apis.base.XeroAPIClient.refresh_access_token",
				return_value=True,
			),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.base import XeroAPIClient

			client = XeroAPIClient()
			result = client.make_request("GET", "/Contacts")

		self.assertEqual(result, {"Contacts": []})

	def test_non_200_response_raises_exception(self):
		mock_settings = _mock_settings()
		mock_response = MagicMock()
		mock_response.status_code = 500
		mock_response.text = "Internal Server Error"

		with (
			patch(SETTINGS_PATH, return_value=mock_settings),
			patch(REQUESTS_GET, return_value=mock_response),
			patch(
				"xero_erpnext_integration.xero_erpnext_integration.apis.base.XeroAPIClient._ensure_valid_token"
			),
			patch("xero_erpnext_integration.xero_erpnext_integration.apis.base.XeroAPIClient._log_request"),
			patch("xero_erpnext_integration.xero_erpnext_integration.apis.base.XeroAPIClient._log_response"),
		):
			from xero_erpnext_integration.xero_erpnext_integration.apis.base import XeroAPIClient

			client = XeroAPIClient()
			self.assertRaises(Exception, client.make_request, "GET", "/Invoices")
