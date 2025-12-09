import frappe

from .base import get_xero_client


@frappe.whitelist()
def authorize():
	"""Exchange authorization code for access token"""
	try:
		# Get Xero Settings
		settings = frappe.get_single("Xero Settings")

		# Validate required fields
		if not settings.code:
			return {"status": "error", "message": "Authorization code is missing. Please authorize again."}

		if not settings.client_id or not settings.get_password("client_secret"):
			return {"status": "error", "message": "Client ID or Client Secret is missing in Xero Settings."}

		# Initialize client and exchange code for token
		client = get_xero_client()
		token_data = client.exchange_code_for_token()  # Returns token data or raises exception

		# If we reach here, the token exchange was successful
		# Test the connection using the new tokens
		# test_result = test_connection_with_token(token_data["access_token"], token_data["tenant_id"])

		if token_data.get("status") == "success":
			return {
				"status": "success",
				"message": "Authorization successful! Connection established with Xero.",
				"token_data": token_data,
				"organization": token_data.get("data", {}),
				"save_required": True,  # Signal frontend to save
			}
		else:
			return {
				"status": "error",
				"message": f"Authorization completed but connection test failed: {token_data.get('message', 'Unknown error')}",
			}

	except Exception as e:
		error_msg = str(e)
		frappe.log_error(f"Xero Authorization Error: {error_msg}", "Xero Authorization")

		# Provide specific error messages for common issues
		if "invalid_grant" in error_msg.lower():
			return {
				"status": "error",
				"message": "Authorization code has expired or already been used. Please click 'Authorize' to get a new authorization code.",
			}
		elif "400" in error_msg and "bad request" in error_msg.lower():
			return {
				"status": "error",
				"message": "Invalid authorization request. Please check your Client ID and Client Secret, then try authorizing again.",
			}
		elif "401" in error_msg or "unauthorized" in error_msg.lower():
			return {
				"status": "error",
				"message": "Invalid Client ID or Client Secret. Please check your Xero app credentials.",
			}
		else:
			return {
				"status": "error",
				"message": f"Authorization error: {error_msg}. Please try authorizing again.",
			}


def test_connection_simple():
	"""Simple connection test for authorization validation"""
	try:
		client = get_xero_client()
		response = client.make_request("GET", "/Organisation")

		if response and response.get("Organisations"):
			org = response["Organisations"][0]
			return {
				"status": "success",
				"data": {
					"name": org.get("Name"),
					"country_code": org.get("CountryCode"),
					"currency_code": org.get("BaseCurrency"),
				},
			}
		else:
			return {"status": "error", "message": "No organisation data received"}

	except Exception as e:
		return {"status": "error", "message": str(e)}


def test_connection_with_token(access_token, tenant_id):
	"""Test connection with specific token and tenant"""
	try:
		import requests

		headers = {
			"Authorization": f"Bearer {access_token}",
			"Xero-Tenant-Id": tenant_id,
			"Accept": "application/json",
		}

		response = requests.get("https://api.xero.com/api.xro/2.0/Organisation", headers=headers)

		if response.status_code == 200:
			data = response.json()
			if data.get("Organisations"):
				org = data["Organisations"][0]
				return {
					"status": "success",
					"data": {
						"name": org.get("Name"),
						"country_code": org.get("CountryCode"),
						"currency_code": org.get("BaseCurrency"),
					},
				}

		return {
			"status": "error",
			"message": f"Connection test failed: {response.status_code} - {response.text}",
		}

	except Exception as e:
		return {"status": "error", "message": str(e)}
