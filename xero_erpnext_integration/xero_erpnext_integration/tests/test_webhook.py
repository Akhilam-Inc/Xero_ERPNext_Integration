# Copyright (c) 2025, nasirucode and Contributors
# See license.txt

import base64
import hashlib
import hmac
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

# ---------------------------------------------------------------------------
# handle_intent_to_receive (GET)
# ---------------------------------------------------------------------------


class TestHandleIntentToReceive(FrappeTestCase):
	def _make_get_request(self, challenge=None):
		mock_request = MagicMock()
		mock_request.method = "GET"
		mock_request.args = {"challenge": challenge} if challenge else {}
		return mock_request

	def test_returns_challenge_value_when_present(self):
		mock_request = self._make_get_request(challenge="abc123")

		with patch("frappe.local") as mock_local:
			mock_local.request = mock_request
			from xero_erpnext_integration.xero_erpnext_integration.apis.webhook import (
				handle_intent_to_receive,
			)

			result = handle_intent_to_receive()

		self.assertEqual(result, "abc123")

	def test_returns_400_when_no_challenge(self):
		mock_request = self._make_get_request()

		with patch("frappe.local") as mock_local:
			mock_local.request = mock_request
			mock_local.response = MagicMock()
			from xero_erpnext_integration.xero_erpnext_integration.apis.webhook import (
				handle_intent_to_receive,
			)

			result = handle_intent_to_receive()

		self.assertEqual(result, "Bad Request")


# ---------------------------------------------------------------------------
# handle_webhook_event (POST)
# ---------------------------------------------------------------------------


class TestHandleWebhookEvent(FrappeTestCase):
	def _build_signature(self, secret, body):
		hashed = hmac.new(bytes(secret, "utf8"), body, hashlib.sha256)
		return base64.b64encode(hashed.digest()).decode("utf-8")

	def test_returns_401_when_signature_missing(self):
		mock_request = MagicMock()
		mock_request.headers = {}
		mock_request.data = b"{}"

		mock_settings = MagicMock()
		mock_settings.webhook_secret = "test-secret"

		with patch("frappe.get_single", return_value=mock_settings), patch("frappe.local") as mock_local:
			mock_local.request = mock_request
			mock_local.response = MagicMock()
			from xero_erpnext_integration.xero_erpnext_integration.apis.webhook import (
				handle_webhook_event,
			)

			result = handle_webhook_event()

		self.assertEqual(result, "Unauthorized")

	def test_returns_401_when_signature_invalid(self):
		body = b'{"events":[]}'
		mock_request = MagicMock()
		mock_request.headers = {"X-Xero-Signature": "invalid-sig"}
		mock_request.data = body

		mock_settings = MagicMock()
		mock_settings.webhook_secret = "test-secret"

		with patch("frappe.get_single", return_value=mock_settings), patch("frappe.local") as mock_local:
			mock_local.request = mock_request
			mock_local.response = MagicMock()
			from xero_erpnext_integration.xero_erpnext_integration.apis.webhook import (
				handle_webhook_event,
			)

			result = handle_webhook_event()

		self.assertEqual(result, "Unauthorized")

	def test_returns_ok_with_valid_signature_and_no_events(self):
		secret = "test-secret"
		body = b'{"events":[]}'
		sig = self._build_signature(secret, body)

		mock_request = MagicMock()
		mock_request.headers = {"X-Xero-Signature": sig}
		mock_request.data = body
		mock_request.json = {"events": []}

		mock_settings = MagicMock()
		mock_settings.webhook_secret = secret

		with patch("frappe.get_single", return_value=mock_settings), patch("frappe.local") as mock_local:
			mock_local.request = mock_request
			mock_local.response = MagicMock()
			from xero_erpnext_integration.xero_erpnext_integration.apis.webhook import (
				handle_webhook_event,
			)

			result = handle_webhook_event()

		self.assertEqual(result, "OK")


# ---------------------------------------------------------------------------
# process_webhook_event
# ---------------------------------------------------------------------------


class TestProcessWebhookEvent(FrappeTestCase):
	def test_invoice_update_event_triggers_update(self):
		event = {
			"eventCategory": "INVOICE",
			"eventType": "UPDATE",
			"resourceId": "xero-invoice-id",
		}

		with patch(
			"xero_erpnext_integration.xero_erpnext_integration.apis.webhook.update_invoice_from_xero"
		) as mock_update:
			from xero_erpnext_integration.xero_erpnext_integration.apis.webhook import process_webhook_event

			process_webhook_event(event)

		mock_update.assert_called_once_with("xero-invoice-id")

	def test_non_invoice_event_is_ignored(self):
		event = {
			"eventCategory": "CONTACT",
			"eventType": "UPDATE",
			"resourceId": "xero-contact-id",
		}

		with patch(
			"xero_erpnext_integration.xero_erpnext_integration.apis.webhook.update_invoice_from_xero"
		) as mock_update:
			from xero_erpnext_integration.xero_erpnext_integration.apis.webhook import process_webhook_event

			process_webhook_event(event)

		mock_update.assert_not_called()
