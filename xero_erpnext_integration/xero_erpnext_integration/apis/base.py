import base64
import json
from datetime import datetime, timedelta
from enum import Enum
from urllib.parse import urljoin

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

		# OAuth 2.0 settings
		self.client_id = self.settings.client_id
		self.client_secret = self.settings.get_password("client_secret")
		self.redirect_uri = self.settings.redirect_uri
		self.scope = "accounting.transactions accounting.contacts accounting.settings offline_access"

		# Current session tokens
		self.access_token = self.settings.access_token
		self.refresh_token = self.settings.refresh_token
		self.tenant_id = self.settings.tenant_id

		# Initialize headers
		self.headers = {"Content-Type": "application/json", "Accept": "application/json"}

		if self.access_token:
			self.headers["Authorization"] = f"Bearer {self.access_token}"

		if self.tenant_id:
			self.headers["Xero-Tenant-Id"] = self.tenant_id

	def get_authorization_url(self, state=None):
		"""Generate OAuth 2.0 authorization URL"""
		try:
			if not self.client_id or not self.redirect_uri:
				frappe.throw(_("Client ID and Redirect URI are required"))

			params = {
				"response_type": "code",
				"client_id": self.client_id,
				"redirect_uri": self.redirect_uri,
				"scope": self.scope,
				"state": state or frappe.generate_hash(length=10),
			}

			query_string = "&".join([f"{k}={v}" for k, v in params.items()])
			return f"{self.auth_url}?{query_string}"

		except Exception as e:
			frappe.log_error(f"Failed to generate authorization URL: {str(e)}", "Xero Auth URL")
			raise

	def exchange_code_for_token(self, state=None):
		"""Exchange authorization code for access token"""
		try:
			# Validate required fields
			if not self.settings.code:
				frappe.log_error("No authorization code available", "Xero Token Exchange")
				return False

			if not self.client_id or not self.client_secret:
				frappe.log_error("Missing client credentials", "Xero Token Exchange")
				return False

			if not self.redirect_uri:
				frappe.log_error("Missing redirect URI", "Xero Token Exchange")
				return False

			# Prepare token request
			token_data = {
				"grant_type": "authorization_code",
				"code": self.settings.code,
				"redirect_uri": self.redirect_uri,
			}

			# Create basic auth header
			auth_header = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()

			headers = {
				"Authorization": f"Basic {auth_header}",
				"Content-Type": "application/x-www-form-urlencoded",
			}

			# Log request details (without sensitive info)

			# Make token request
			response = requests.post(self.token_url, data=token_data, headers=headers)

			# Log the response status for debugging

			# Handle successful responses (200-299 range)
			if 200 <= response.status_code < 300:
				try:
					token_response = response.json()
				except ValueError as e:
					frappe.log_error(
						f"Invalid JSON in token response: {response.text}", "Xero Token Exchange"
					)
					raise Exception(f"Invalid response format from Xero: {str(e)}")

				# Validate response contains required tokens
				if not token_response.get("access_token"):
					frappe.log_error(f"No access token in response: {token_response}", "Xero Token Exchange")
					raise Exception("No access token received from Xero")

				# Save tokens to settings object (but don't persist yet)
				access_token = token_response.get("access_token")
				refresh_token = token_response.get("refresh_token")
				scope = token_response.get("scope")
				expires_in = token_response.get("expires_in", 1800)

				self.settings.access_token = access_token
				self.settings.refresh_token = refresh_token
				self.settings.scope = scope

				# Calculate expiry time
				expires_at = datetime.now() + timedelta(seconds=expires_in)
				self.settings.token_expires_at = expires_at

				# Update headers with new access token for tenant info call
				self.access_token = access_token
				self.headers["Authorization"] = f"Bearer {access_token}"

				# Get tenant information
				self._get_and_save_tenant_info()

				# Ensure we got tenant information
				if not self.settings.tenant_id:
					frappe.log_error("No tenant ID received from Xero connections", "Xero Token Exchange")
					raise Exception("Failed to get tenant information from Xero")

				# Return complete token data
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

			# Handle specific error status codes
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

					frappe.log_error(f"400 Error: {error_response}", "Xero Token Exchange")
					raise Exception(error_msg)
				except ValueError:
					error_msg = f"Bad request (400): {response.text}"
					frappe.log_error(error_msg, "Xero Token Exchange")
					raise Exception(error_msg)

			elif response.status_code == 401:
				error_msg = "Unauthorized - Invalid Client ID or Client Secret"
				frappe.log_error(f"401 Error: {response.text}", "Xero Token Exchange")
				raise Exception(error_msg)

			elif response.status_code == 403:
				error_msg = "Forbidden - Client not authorized for this operation"
				frappe.log_error(f"403 Error: {response.text}", "Xero Token Exchange")
				raise Exception(error_msg)

			elif response.status_code == 429:
				error_msg = "Rate limit exceeded - Please try again later"
				frappe.log_error(f"429 Error: {response.text}", "Xero Token Exchange")
				raise Exception(error_msg)

			elif response.status_code >= 500:
				error_msg = f"Xero server error ({response.status_code}) - Please try again later"
				frappe.log_error(
					f"Server Error: {response.status_code} - {response.text}", "Xero Token Exchange"
				)
				raise Exception(error_msg)

			else:
				error_msg = f"Unexpected response ({response.status_code}): {response.text}"
				frappe.log_error(error_msg, "Xero Token Exchange")
				raise Exception(error_msg)

		except Exception as e:
			error_details = f"Token exchange error: {str(e)}"
			frappe.log_error(error_details, "Xero Token Exchange")
			raise  # Re-raise to let calling function handle it

	def _get_and_save_tenant_info(self):
		"""Get tenant information and save to settings"""
		try:
			# Headers should already be updated with access token in calling method
			# Just ensure we have the authorization header
			if "Authorization" not in self.headers or not self.access_token:
				frappe.log_error("No access token available for tenant info request", "Xero Tenant Info")
				return

			# Get connections (tenants)
			response = requests.get(self.connections_url, headers=self.headers)

			if response.status_code == 200:
				connections = response.json()

				if connections and len(connections) > 0:
					# Use first connection as default
					connection = connections[0]
					tenant_id = connection.get("tenantId")
					tenant_name = connection.get("tenantName")

					self.settings.tenant_id = tenant_id
					self.settings.tenant_name = tenant_name

					# Update headers with tenant ID for future requests
					self.headers["Xero-Tenant-Id"] = tenant_id

				else:
					frappe.log_error("No tenant connections available", "Xero Tenant Info")
			else:
				frappe.log_error(
					f"Failed to get tenant info: {response.status_code} - {response.text}", "Xero Tenant Info"
				)

		except Exception as e:
			frappe.log_error(f"Failed to get tenant info: {str(e)}", "Xero Tenant Info")

	def refresh_access_token(self):
		"""Refresh access token using refresh token"""
		try:
			if not self.refresh_token:
				return False

			token_data = {
				"grant_type": "refresh_token",
				"refresh_token": self.refresh_token,
				"client_id": self.client_id,
				"client_secret": self.client_secret,
			}

			auth_header = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()

			headers = {
				# "Authorization": f"Basic {auth_header}",
				"Content-Type": "application/x-www-form-urlencoded"
			}

			response = requests.post(self.token_url, data=token_data, headers=headers)

			if response.status_code == 200:
				token_data = response.json()

				# Update tokens
				self.settings.access_token = token_data.get("access_token")
				if token_data.get("refresh_token"):
					self.settings.refresh_token = token_data.get("refresh_token")

				# Update expiry
				expires_in = token_data.get("expires_in", 1800)
				expires_at = datetime.now() + timedelta(seconds=expires_in)
				self.settings.token_expires_at = expires_at

				# Save settings
				self.settings.save()

				# Update headers
				self.access_token = self.settings.access_token
				self.headers["Authorization"] = f"Bearer {self.access_token}"

				return True
			else:
				frappe.log_error(
					title="Xero Token Refresh",
					message=f"Token refresh failed: {response.text}",
				)
				return False

		except Exception as e:
			frappe.log_error(title="Xero Token Refresh", message=f"Token refresh error: {str(e)}")
			return False

	def _ensure_valid_token(self):
		"""Ensure we have a valid access token"""
		if not self.access_token:
			frappe.throw(_("No access token available. Please authorize the application."))

		# Check if token is expired
		if self.settings.token_expires_at:
			expires_at = self.settings.token_expires_at
			if isinstance(expires_at, str):
				expires_at = datetime.fromisoformat(expires_at)

			# Refresh if expires in next 5 minutes
			if datetime.now() >= expires_at - timedelta(minutes=5):
				if not self.refresh_access_token():
					frappe.throw(_("Failed to refresh access token. Please re-authorize the application."))

	def make_request(self, method, endpoint, data=None, params=None):
		"""Make authenticated request to Xero API"""
		response = None
		try:
			# Ensure valid token
			self._ensure_valid_token()

			# Build URL
			url = f"{self.base_url}/{endpoint.lstrip('/')}"

			# Prepare request
			request_headers = self.headers.copy()

			# Log request

			# Make request
			if method.upper() == "GET":
				response = requests.get(url, headers=request_headers, params=params)
			elif method.upper() == "POST":
				response = requests.post(url, headers=request_headers, json=data, params=params)
			elif method.upper() == "PUT":
				response = requests.put(url, headers=request_headers, json=data, params=params)
			elif method.upper() == "DELETE":
				response = requests.delete(url, headers=request_headers, params=params)
			else:
				frappe.throw(_("Unsupported HTTP method: {0}").format(method))

			# Log response
			self._log_request(method, url, data, params, response)

			# Handle response
			if response.status_code in [200, 201]:
				try:
					return response.json()
				except:
					return {"message": "Success", "data": response.text}
			elif response.status_code == 401:
				# Try to refresh token and retry once
				if self.refresh_access_token():
					request_headers["Authorization"] = f"Bearer {self.access_token}"

					# Retry request
					if method.upper() == "GET":
						response = requests.get(url, headers=request_headers, params=params)
					elif method.upper() == "POST":
						response = requests.post(url, headers=request_headers, json=data, params=params)
					elif method.upper() == "PUT":
						response = requests.put(url, headers=request_headers, json=data, params=params)
					elif method.upper() == "DELETE":
						response = requests.delete(url, headers=request_headers, params=params)

					if response.status_code in [200, 201]:
						try:
							return response.json()
						except:
							return {"message": "Success", "data": response.text}

				frappe.throw(_("Authentication failed. Please re-authorize the application."))
			else:
				error_msg = f"API request failed: {response.status_code} - {response.text}"
				frappe.throw(_(error_msg))

		except Exception as e:
			self._log_response(response)
			frappe.log_error(title="Xero API Request", message=f"API request failed: {str(e)}")
			raise

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

			# Test API call - get organisation info
			response = self.make_request("GET", "Organisation")

			if response and "Organisations" in response:
				org = response["Organisations"][0] if response["Organisations"] else {}
				return {
					"status": "success",
					"message": "Connection successful",
					"organisation": {
						"name": org.get("Name"),
						"country_code": org.get("CountryCode"),
						"currency_code": org.get("BaseCurrency"),
					},
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
			frappe.log_error(f"Failed to create invoice: {str(e)}", "Xero Create Invoice")
			return None

	def get_invoice(self, invoice_id):
		"""Get invoice from Xero"""
		try:
			response = self.make_request("GET", f"Invoices/{invoice_id}")

			if response and "Invoices" in response:
				return response["Invoices"][0]
			return None

		except Exception as e:
			frappe.log_error(f"Failed to get invoice: {str(e)}", "Xero Get Invoice")
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
			frappe.log_error(f"Failed to get payments: {str(e)}", "Xero Get Payments")
			return []

	def _log_request(self, method, url, data, params, response):
		"""Log API request"""
		if not self.settings.debug_mode:
			return

		try:
			# Determine message based on response status
			message = "Success"
			if response:
				if response.status_code >= 400:
					message = "Error"
				elif response.status_code >= 300:
					message = "Redirect"
			else:
				message = "No Response"

			# Prepare headers for logging (exclude sensitive information)
			headers_to_log = self.headers.copy()
			if "Authorization" in headers_to_log:
				# Mask the token for security
				auth_header = headers_to_log["Authorization"]
				if "Bearer" in auth_header:
					headers_to_log["Authorization"] = "Bearer ***MASKED***"
				elif "Basic" in auth_header:
					headers_to_log["Authorization"] = "Basic ***MASKED***"

			log_data = {
				"doctype": "Xero API Log",
				"api_method": method,
				"api_url": url,
				"message": message,
				"headers": json.dumps(headers_to_log, indent=2),
				"payload": json.dumps({"data": data, "params": params}, indent=2) if (data or params) else "",
				"timestamp": frappe.utils.now(),
				"status_code": str(response.status_code) if response else "",
				"response": json.dumps(response.json(), indent=2)
				if response and response.status_code < 400
				else (response.text if response else ""),
			}

			frappe.get_doc(log_data).insert(ignore_permissions=True)

		except Exception as e:
			frappe.log_error(f"Failed to log request: {str(e)}", "Xero Request Log")
			return

	def _log_response(self, response):
		"""Log API response"""
		if not self.settings.debug_mode:
			return

		try:
			# Find the most recent log entry to update
			logs = frappe.get_all(
				"Xero API Log", filters={"tenant_id": self.tenant_id}, order_by="creation desc", limit=1
			)

			if logs:
				log_doc = frappe.get_doc("Xero API Log", logs[0].name)
				log_doc.status_code = str(response.status_code)
				log_doc.message = "Success" if response.status_code < 400 else "Error"

				try:
					log_doc.response_data = json.dumps(response.json(), indent=2)
				except:
					log_doc.response_data = response.text

				log_doc.save(ignore_permissions=True)

		except Exception as e:
			frappe.log_error(f"Failed to log response: {str(e)}", "Xero Response Log")


# Utility function to get Xero client
@frappe.whitelist()
def get_xero_client():
	"""Get configured Xero API client"""
	return XeroAPIClient()
