import base64
import json
from datetime import datetime, timedelta
from enum import Enum
from urllib.parse import urlencode, urljoin

import frappe
import requests
from frappe import _
from frappe.utils.background_jobs import enqueue


class SupportedHTTPMethod(Enum):
	GET = "GET"
	POST = "POST"
	PUT = "PUT"
	PATCH = "PATCH"
	DELETE = "DELETE"


# Scopes required for invoices, contacts, and tax rates (/TaxRates needs accounting.settings).
XERO_DEFAULT_SCOPE = (
	"openid profile email offline_access "
	"accounting.transactions accounting.contacts accounting.settings"
)


class XeroAPIClient:
	"""
	Xero API Client for OAuth 2.0 authentication and API calls
	"""

	def __init__(self):
		self.settings = frappe.get_single("Xero Settings")
		self.base_url = "https://api.xero.com/api.xro/2.0"
		self.auth_url = "https://login.xero.com/identity/connect/authorize"
		self.token_url = "https://identity.xero.com/connect/token"
		self.connections_url = "https://api.xero.com/connections"

		self.client_id = self.settings.client_id
		self.client_secret = self._safe_get_password("client_secret")
		# Use stored redirect_uri if set; otherwise derive from site URL (tunnel or host_name in site config)
		self.redirect_uri = self.settings.redirect_uri or frappe.utils.get_url("/desk/xero-settings")
		self.scope = "accounting.transactions accounting.contacts accounting.settings offline_access"

		self.access_token = self._safe_get_password("access_token")
		self.refresh_token = self._safe_get_password("refresh_token")
		self.tenant_id = self.settings.tenant_id

		self.headers = {"Content-Type": "application/json", "Accept": "application/json"}
		if self.access_token:
			self.headers["Authorization"] = f"Bearer {self.access_token}"
		if self.tenant_id:
			self.headers["Xero-Tenant-Id"] = self.tenant_id

	def _reload_credentials_from_db(self):
		"""Reload tokens/tenant from Xero Settings and rebuild API headers."""
		self.settings.reload()
		self.access_token = self._safe_get_password("access_token") or ""
		self.refresh_token = self._safe_get_password("refresh_token") or ""
		self.tenant_id = (self.settings.tenant_id or "").strip()
		self.client_secret = self._safe_get_password("client_secret")
		self.headers = {
			"Content-Type": "application/json",
			"Accept": "application/json",
		}
		if self.access_token:
			self.headers["Authorization"] = f"Bearer {self.access_token}"
		if self.tenant_id:
			self.headers["Xero-Tenant-Id"] = self.tenant_id

	def _safe_get_password(self, field):
		"""Return the decrypted password field value, or None if not yet set."""
		return self.settings.get_password(field, raise_exception=False) or None

	def _validate_api_prerequisites(self):
		"""Fail fast with a clear message before calling the Xero API."""
		if not self.settings.enable:
			frappe.throw(_("Xero integration is disabled in Xero Settings."))
		if not self.access_token:
			frappe.throw(_("No access token. Please authorize from Xero Settings."))
		if not self.refresh_token:
			frappe.throw(_("No refresh token. Please re-authorize from Xero Settings."))
		if not self.tenant_id:
			frappe.throw(
				_(
					"Xero Tenant ID is missing. Open Xero Settings and click Authorize again "
					"so the tenant connection is saved."
				)
			)
		if not self.client_id or not self.client_secret:
			frappe.throw(_("Client ID or Client Secret is missing in Xero Settings."))

	def get_authorization_url(self, state=None):
		"""Generate OAuth 2.0 authorization URL"""
		try:
			if not self.client_id or not self.redirect_uri:
				frappe.throw(_("Client ID and Redirect URI are required"))

			params = {
				"response_type": "code",
				"client_id": self.client_id,
				"redirect_uri": self.redirect_uri,
				"scope": self.scope or XERO_DEFAULT_SCOPE,
				"state": state or frappe.generate_hash(length=10),
			}

			# A11 fix: use urlencode to properly encode all param values (especially redirect_uri)
			return f"{self.auth_url}?{urlencode(params)}"

		except Exception as e:
			frappe.log_error(title="Xero Auth URL", message=f"Failed to generate authorization URL: {e!s}")
			raise

	def exchange_code_for_token(self, state=None):
		"""Exchange authorization code for access token"""
		try:
			if not self.settings.code:
				frappe.log_error(title="Xero Token Exchange", message="No authorization code available")
				return False

			if not self.client_id or not self.client_secret:
				frappe.log_error(title="Xero Token Exchange", message="Missing client credentials")
				return False

			if not self.redirect_uri:
				frappe.log_error(title="Xero Token Exchange", message="Missing redirect URI")
				return False

			token_request = {
				"grant_type": "authorization_code",
				"code": self.settings.code,
				"redirect_uri": self.redirect_uri,
			}

			auth_header = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()

			headers = {
				"Authorization": f"Basic {auth_header}",
				"Content-Type": "application/x-www-form-urlencoded",
			}

			response = requests.post(self.token_url, data=token_request, headers=headers)

			if 200 <= response.status_code < 300:
				try:
					token_response = response.json()
				except ValueError as e:
					frappe.log_error(
						title="Xero Token Exchange",
						message=f"Invalid JSON in token response: {response.text}",
					)
					raise Exception(f"Invalid response format from Xero: {e!s}")

				if not token_response.get("access_token"):
					frappe.log_error(
						title="Xero Token Exchange",
						message=f"No access token in response: {token_response}",
					)
					raise Exception("No access token received from Xero")

				access_token = token_response.get("access_token")
				refresh_token = token_response.get("refresh_token")
				scope = token_response.get("scope")
				expires_in = token_response.get("expires_in", 1800)

				self.settings.access_token = access_token
				self.settings.refresh_token = refresh_token
				self.settings.scope = scope or XERO_DEFAULT_SCOPE

				expires_at = datetime.now() + timedelta(seconds=expires_in)
				self.settings.token_expires_at = expires_at.isoformat()

				self.access_token = access_token
				self.refresh_token = refresh_token
				self.headers["Authorization"] = f"Bearer {access_token}"

				self._get_and_save_tenant_info()

				if not self.settings.tenant_id:
					frappe.log_error(
						title="Xero Token Exchange",
						message="No tenant ID received from Xero connections",
					)
					raise Exception("Failed to get tenant information from Xero")

				# A10 fix: save settings so tokens are persisted to DB, then clear cache
				self.settings.save()
				frappe.clear_document_cache("Xero Settings", "Xero Settings")

				return {
					"access_token": access_token,
					"refresh_token": refresh_token,
					"scope": scope,
					"expires_in": expires_in,
					"expires_at": expires_at.isoformat(),
					"tenant_id": self.settings.tenant_id,
					"tenant_name": self.settings.tenant_name,
					"status": "success",
				}

			elif response.status_code == 400:
				try:
					error_response = response.json()
					error_type = error_response.get("error", "bad_request")
					error_description = error_response.get("error_description", response.text)

					if error_type == "invalid_grant":
						error_msg = "Authorization code has expired or already been used"
					elif error_type == "invalid_client":
						error_msg = "Invalid Client ID or Client Secret"
					elif error_type == "invalid_request":
						error_msg = "Invalid authorization request - check redirect URI"
					else:
						error_msg = f"Bad request: {error_description}"

					frappe.log_error(title="Xero Token Exchange", message=f"400 Error: {error_response}")
					raise Exception(error_msg)
				except ValueError:
					error_msg = f"Bad request (400): {response.text}"
					frappe.log_error(title="Xero Token Exchange", message=error_msg)
					raise Exception(error_msg)

			elif response.status_code == 401:
				error_msg = "Unauthorized - Invalid Client ID or Client Secret"
				frappe.log_error(title="Xero Token Exchange", message=f"401 Error: {response.text}")
				raise Exception(error_msg)

			elif response.status_code == 403:
				error_msg = "Forbidden - Client not authorized for this operation"
				frappe.log_error(title="Xero Token Exchange", message=f"403 Error: {response.text}")
				raise Exception(error_msg)

			elif response.status_code == 429:
				error_msg = "Rate limit exceeded - Please try again later"
				frappe.log_error(title="Xero Token Exchange", message=f"429 Error: {response.text}")
				raise Exception(error_msg)

			elif response.status_code >= 500:
				error_msg = f"Xero server error ({response.status_code}) - Please try again later"
				frappe.log_error(
					title="Xero Token Exchange",
					message=f"Server Error: {response.status_code} - {response.text}",
				)
				raise Exception(error_msg)

			else:
				error_msg = f"Unexpected response ({response.status_code}): {response.text}"
				frappe.log_error(title="Xero Token Exchange", message=error_msg)
				raise Exception(error_msg)

		except Exception as e:
			frappe.log_error(title="Xero Token Exchange", message=f"Token exchange error: {e!s}")
			raise

	def _get_and_save_tenant_info(self):
		"""Get tenant information and save to settings"""
		try:
			if "Authorization" not in self.headers or not self.access_token:
				frappe.log_error(
					title="Xero Tenant Info",
					message="No access token available for tenant info request",
				)
				return

			response = requests.get(self.connections_url, headers=self.headers)

			if response.status_code == 200:
				connections = response.json()

				if connections and len(connections) > 0:
					connection = connections[0]
					tenant_id = connection.get("tenantId")
					tenant_name = connection.get("tenantName")

					self.settings.tenant_id = tenant_id
					self.settings.tenant_name = tenant_name

					self.headers["Xero-Tenant-Id"] = tenant_id

				else:
					frappe.log_error(
						title="Xero Tenant Info",
						message="No tenant connections available",
					)
			else:
				frappe.log_error(
					title="Xero Tenant Info",
					message=f"Failed to get tenant info: {response.status_code} - {response.text}",
				)

		except Exception as e:
			frappe.log_error(title="Xero Tenant Info", message=f"Failed to get tenant info: {e!s}")

	def _persist_tokens_to_settings(self):
		"""Write current tokens/tenant to Xero Settings and refresh in-memory headers."""
		self.settings.flags.ignore_permissions = True
		self.settings.save()
		frappe.db.commit()
		self._reload_credentials_from_db()

	def refresh_access_token(self):
		"""Refresh access token using refresh token (Xero requires HTTP Basic auth)."""
		try:
			# Always read the latest refresh token from DB (may have been rotated).
			self._reload_credentials_from_db()

			if not self.refresh_token:
				frappe.log_error("No refresh token in Xero Settings", "Xero Token Refresh")
				return False

			if not self.client_id or not self.client_secret:
				frappe.log_error("Missing client_id or client_secret", "Xero Token Refresh")
				return False

			# A6 fix: renamed dict to refresh_payload to avoid collision with response.json() below
			refresh_payload = {
				"grant_type": "refresh_token",
				"refresh_token": self.refresh_token,
			}

			headers = {"Content-Type": "application/x-www-form-urlencoded"}

			response = requests.post(self.token_url, data=refresh_payload, headers=headers)

			if response.status_code == 200:
				token_response = response.json()

				self.settings.access_token = token_response.get("access_token")
				if token_response.get("refresh_token"):
					self.settings.refresh_token = token_response.get("refresh_token")

				expires_in = token_response.get("expires_in", 1800)
				expires_at = datetime.now() + timedelta(seconds=expires_in)
				self.settings.token_expires_at = expires_at

				self.settings.save()
				frappe.clear_document_cache("Xero Settings", "Xero Settings")

				self.access_token = self.settings.access_token
				self.headers["Authorization"] = f"Bearer {self.access_token}"

				return True

			frappe.log_error(
				title="Xero Token Refresh",
				message=f"Token refresh failed ({response.status_code}): {response.text}",
			)
			return False

		except Exception as e:
			frappe.log_error(title="Xero Token Refresh", message=f"Token refresh error: {e!s}")
			return False

	def _ensure_valid_token(self):
		"""Refresh the access token if it is expired or about to expire."""
		if not self.access_token:
			frappe.throw(_("No access token available. Please authorize from Xero Settings."))

		if self.settings.token_expires_at:
			expires_at = self.settings.token_expires_at
			if isinstance(expires_at, str):
				expires_at = datetime.fromisoformat(expires_at)

			if datetime.now() >= expires_at - timedelta(minutes=5):
				if not self.refresh_access_token():
					frappe.throw(_("Failed to refresh access token. Please re-authorize the application."))

	def _dispatch(self, method, url, headers, data, params):
		"""Single HTTP dispatch point — avoids duplicating dispatch logic for retry."""
		method = method.upper()
		if method == "GET":
			return requests.get(url, headers=headers, params=params)
		elif method == "POST":
			return requests.post(url, headers=headers, json=data, params=params)
		elif method == "PUT":
			return requests.put(url, headers=headers, json=data, params=params)
		elif method == "DELETE":
			return requests.delete(url, headers=headers, params=params)
		else:
			frappe.throw(_("Unsupported HTTP method: {0}").format(method))

	def make_request(self, method, endpoint, data=None, params=None):
		"""Make authenticated request to Xero API"""
		response = None
		token_refreshed = False
		try:
			self._ensure_valid_token()
			self._reload_credentials_from_db()

			url = f"{self.base_url}/{endpoint.lstrip('/')}"
			request_headers = self.headers.copy()

			# C8 fix: extracted _dispatch() — no duplicate dispatch blocks
			response = self._dispatch(method, url, request_headers, data, params)

			self._log_request(method, url, data, params, response)

			if response.status_code in [200, 201]:
				try:
					return response.json()
				except ValueError:
					return {"message": "Success", "data": response.text}

			if response.status_code == 401 and not token_refreshed:
				# One refresh + retry (401 often means expired token OR missing scope/tenant).
				if not self.refresh_access_token():
					self._raise_auth_error(
						response,
						_(
							"Xero rejected the request and the refresh token could not be renewed. "
							"Re-authorize from Xero Settings."
						),
					)

				token_refreshed = True
				self._reload_credentials_from_db()
				request_headers = self.headers.copy()
				response = self._dispatch(method, url, request_headers, data, params)
				self._log_request(method, url, data, params, response)

			if response.status_code in [200, 201]:
				try:
					return response.json()
				except Exception:
					return {"message": "Success", "data": response.text}

			self._raise_auth_error(
				response,
				_(
					"Xero still rejected the request after refreshing the token. "
					"Re-authorize from Xero Settings and ensure scope includes "
					"'accounting.settings' (required for Tax Rates)."
				),
			)

			self._raise_xero_error(response)

		except Exception as e:
			# A5 fix: guard against response being None before passing to _log_response
			if response is not None:
				self._log_response(response)
			frappe.log_error(title="Xero API Request", message=f"API request failed: {e!s}")
			raise

	def _raise_auth_error(self, response, prefix_message):
		"""Throw with the real Xero response body when auth keeps failing."""
		detail = ""
		if response is not None:
			try:
				payload = response.json()
				detail = (
					payload.get("Detail")
					or payload.get("Title")
					or payload.get("Message")
					or payload.get("error_description")
					or response.text
				)
			except Exception:
				detail = response.text or ""

		granted_scope = (self.settings.scope or "").lower()
		scope_hint = ""
		if "accounting.settings" not in granted_scope:
			scope_hint = (
				" Your saved scope does not include 'accounting.settings', which is required "
				"for Tax Rates. Click Authorize in Xero Settings again."
			)

		frappe.throw(_(f"{prefix_message}{scope_hint} {detail}".strip()))

	def _raise_xero_error(self, response):
		"""Build a concise error message from a failed Xero response and throw."""
		status = response.status_code if response is not None else "?"
		text = response.text if response is not None else ""
		error_msg = f"API request failed: {status} - {text}"

		try:
			payload = response.json()
		except Exception:
			payload = None

		if isinstance(payload, dict):
			# Standard Xero validation error envelope
			elements = payload.get("Elements") or []
			validation_errors = (elements[0] or {}).get("ValidationErrors") if elements else None
			if validation_errors:
				msgs = [ve.get("Message") for ve in validation_errors if ve.get("Message")]
				if msgs:
					error_msg = "Xero validation error: " + " ; ".join(msgs)

			# OAuth/scope-style error
			problem = payload.get("Title") or payload.get("Detail") or payload.get("error_description")
			if problem and "validation" not in error_msg.lower():
				error_msg = f"Xero error ({status}): {problem}"

			# Plain `Message` field used by some endpoints
			if not validation_errors and payload.get("Message"):
				error_msg = f"Xero error ({status}): {payload.get('Message')}"

		# Hint when the access token was issued without accounting.settings scope
		if status == 403 and "scope" not in error_msg.lower():
			error_msg += " (If you recently added Tax Rate sync, re-authorize Xero so the new 'accounting.settings' scope is granted.)"

		frappe.throw(_(error_msg))

	def test_connection(self):
		"""Test connection to Xero API"""
		try:
			if not self.settings.enable:
				return {"status": "error", "message": "Xero integration is not enabled"}

			if not self.access_token:
				return {
					"status": "error",
					"message": "No access token. Please authorize the application first.",
				}

			if not self.tenant_id:
				return {"status": "error", "message": "No tenant selected. Please complete authorization."}

			# Test organisation + tax rates (tax rates need accounting.settings scope).
			org_response = self.make_request("GET", "Organisation")
			tax_response = self.make_request("GET", "TaxRates")

			if org_response and "Organisations" in org_response:
				org = org_response["Organisations"][0] if org_response["Organisations"] else {}
				tax_count = len((tax_response or {}).get("TaxRates") or [])
				scope = self.settings.scope or ""
				has_tax_scope = "accounting.settings" in scope
				return {
					"status": "success",
					"message": f"Connection OK. {tax_count} tax rate(s) readable from Xero.",
					"organisation": {
						"name": org.get("Name"),
						"country_code": org.get("CountryCode"),
						"currency_code": org.get("BaseCurrency"),
					},
					"tax_rates_count": tax_count,
					"scope": scope,
					"has_accounting_settings_scope": has_tax_scope,
				}
			else:
				return {"status": "error", "message": "Failed to retrieve organisation information"}

		except Exception as e:
			return {"status": "error", "message": str(e)}

	def create_invoice(self, invoice_data):
		"""Create invoice in Xero"""
		try:
			data = {"Invoices": [invoice_data]}
			response = self.make_request("POST", "Invoices", data=data)

			if response and "Invoices" in response:
				return response["Invoices"][0]
			return None

		except Exception as e:
			frappe.log_error(title="Xero Create Invoice", message=f"Failed to create invoice: {e!s}")
			return None

	def get_invoice(self, invoice_id):
		"""Get invoice from Xero"""
		try:
			response = self.make_request("GET", f"Invoices/{invoice_id}")

			if response and "Invoices" in response:
				return response["Invoices"][0]
			return None

		except Exception as e:
			frappe.log_error(title="Xero Get Invoice", message=f"Failed to get invoice: {e!s}")
			return None

	def get_payments(self, invoice_id=None):
		"""Get payments from Xero"""
		try:
			params = {}
			if invoice_id:
				params["where"] = f'Invoice.InvoiceID==Guid("{invoice_id}")'

			response = self.make_request("GET", "Payments", params=params)
			return response.get("Payments", []) if response else []

		except Exception as e:
			frappe.log_error(title="Xero Get Payments", message=f"Failed to get payments: {e!s}")
			return []

	def _log_request(self, method, url, data, params, response):
		"""Log API request"""
		# Always log errors; log successes only in debug mode
		if not self.settings.debug_mode and not (response and response.status_code >= 400):
			return

		try:
			message = "Success"
			if response:
				if response.status_code >= 400:
					message = "Error"
				elif response.status_code >= 300:
					message = "Redirect"
			else:
				message = "No Response"

			headers_to_log = self.headers.copy()
			if "Authorization" in headers_to_log:
				auth_header = headers_to_log["Authorization"]
				if "Bearer" in auth_header:
					headers_to_log["Authorization"] = "Bearer ***MASKED***"
				elif "Basic" in auth_header:
					headers_to_log["Authorization"] = "Basic ***MASKED***"

			# C6 fix: wrap response.json() in try/except — non-JSON responses (HTML errors) would crash
			response_body = ""
			if response:
				if response.status_code < 400:
					try:
						response_body = json.dumps(response.json(), indent=2)
					except ValueError:
						response_body = response.text
				else:
					response_body = response.text

			log_data = {
				"doctype": "Xero API Log",
				"api_method": method,
				"api_url": url,
				"message": message,
				"headers": json.dumps(headers_to_log, indent=2),
				"payload": json.dumps({"data": data, "params": params}, indent=2) if (data or params) else "",
				"timestamp": frappe.utils.now(),
				"status_code": str(response.status_code) if response else "",
				"response": response_body,
			}

			frappe.get_doc(log_data).insert(ignore_permissions=True)

		except Exception as e:
			frappe.log_error(title="Xero Request Log", message=f"Failed to log request: {e!s}")
			return

	def _log_response(self, response):
		"""Log API response by updating the most recent Xero API Log entry.

		Note: `Xero API Log` doesn't have a `tenant_id` column, so we simply pick
		the latest log entry created in this request.
		"""
		if not self.settings.debug_mode or response is None:
			return

		try:
			logs = frappe.get_all(
				"Xero API Log",
				fields=["name"],
				order_by="creation desc",
				limit=1,
			)

			if logs:
				log_doc = frappe.get_doc("Xero API Log", logs[0].name)
				log_doc.status_code = str(response.status_code)
				log_doc.message = "Success" if response.status_code < 400 else "Error"

				# A2 fix: field is "response" not "response_data" (confirmed in xero_api_log.json)
				try:
					log_doc.response = json.dumps(response.json(), indent=2)
				except Exception:
					log_doc.response = response.text

				log_doc.save(ignore_permissions=True)

		except Exception as e:
			frappe.log_error(title="Xero Response Log", message=f"Failed to log response: {e!s}")


# Utility function to get Xero client
@frappe.whitelist()
def get_xero_client():
	"""Get configured Xero API client"""
	return XeroAPIClient()
