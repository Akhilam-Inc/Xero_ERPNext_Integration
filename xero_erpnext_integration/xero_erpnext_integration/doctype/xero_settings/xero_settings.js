frappe.ui.form.on("Xero Settings", {
	refresh: function (frm) {
		// Handle authorization callback
		const urlParams = new URLSearchParams(window.location.search);
		const code = urlParams.get("code");

		// Always process new authorization codes from URL
		if (code && code !== frm.doc.code) {
			handle_authorization_callback(frm, code, urlParams.get("scope"));
			return;
		}

		// Add custom buttons
		frm.add_custom_button(__("Authorize"), function () {
			authorize(frm);
		});

		frm.add_custom_button(__("Sync Paid Invoices"), function () {
			sync_paid_invoices(frm);
		});

		// Show connection status
		if (frm.doc.access_token) {
			frm.dashboard.add_indicator(__("Connected"), "green");
		} else {
			frm.dashboard.add_indicator(__("Not Connected"), "red");
		}
	},
});

function handle_authorization_callback(frm, code, scope) {
	// Set the authorization values and process immediately
	frm.set_value("code", code);
	frm.set_value("scope", scope);

	// Process authorization with async/await
	process_authorization(frm);
}

async function process_authorization(frm) {
	if (frm._authorizing) {
		return;
	}
	frm._authorizing = true;
	// Call authorization API and wait for completion
	const response = await new Promise((resolve, reject) => {
		frappe.call({
			method: "xero_erpnext_integration.xero_erpnext_integration.apis.connection.authorize",
			callback: function (r) {
				if (r.message && r.message.status === "success") {
					resolve(r.message);
				} else {
					reject(r.message);
				}
			},
			error: function (r) {
				reject({ message: "Network error during authorization. Please try again." });
			},
		});
	});

	// Authorization successful - update form with token data
	let authorizationSuccessful = false;

	if (response.token_data) {
		const tokenData = response.token_data;
		console.log(tokenData);

		// Check if we actually received an access token
		if (!tokenData.access_token) {
			frappe.show_alert({
				message: __("Authorization failed: No access token received from Xero"),
				indicator: "red",
			});
		} else {
			// Set all token fields
			frm.doc.access_token = tokenData.access_token;
			frm.doc.refresh_token = tokenData.refresh_token;
			frm.doc.scope = tokenData.scope;
			frm.doc.tenant_id = tokenData.tenant_id;
			frm.doc.tenant_name = tokenData.tenant_name;
			frm.doc.enable = 1;

			// Set expiry time from backend calculation
			if (tokenData.expires_at) {
				frm.doc.token_expires_at = tokenData.expires_at;
			}

			// Refresh form to show updated values
			frm.refresh_fields();
			authorizationSuccessful = true;
		}
	} else {
		// No token data received at all
		frappe.show_alert({
			message: __("Authorization failed: No token data received from Xero"),
			indicator: "red",
		});
	}

	// Save the form with all updated values (regardless of success/failure)
	await new Promise((resolve, reject) => {
		frm.save(
			null,
			function () {
				console.log("Save successful");
				resolve();
			},
			function (error) {
				console.log("Save failed:", error);
				reject(error);
			}
		);
	});

	// Show appropriate message based on authorization result
	if (authorizationSuccessful) {
		frappe.show_alert({
			message: __("Authorization Successful!"),
			indicator: "green",
		});
	}

	// Clean up URL parameters
	window.history.replaceState({}, document.title, window.location.pathname);

	// Refresh page to show updated status
	setTimeout(function () {
		window.location.reload();
	}, 1500);
}

function sync_paid_invoices(frm) {
	frappe.call({
		method: "xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.sync_invoice_payments",
		callback: function (r) {
			if (r.message && r.message.status === "success") {
				frappe.show_alert({
					message: __("Paid Invoices Synced Successfully"),
					indicator: "green",
				});
			} else {
				frappe.show_alert({
					message: __("Error Syncing Paid Invoices"),
					indicator: "red",
				});
			}
		},
	});
}

function authorize(frm) {
	// Validate required fields
	if (!frm.doc.client_id) {
		frappe.show_alert({
			message: __("Please enter the Client ID before authorizing."),
			indicator: "red",
		});
		return;
	}

	if (!frm.doc.redirect_uri) {
		frappe.show_alert({
			message: __("Please enter the Redirect URI before authorizing."),
			indicator: "red",
		});
		return;
	}

	// Generate state if not exists
	const state = frm.doc.state || Math.random().toString(36).substring(2, 15);
	if (!frm.doc.state) {
		frm.set_value("state", state);
	}

	// Build authorization URL
	const authUrl =
		"https://login.xero.com/identity/connect/authorize?" +
		new URLSearchParams({
			response_type: "code",
			client_id: frm.doc.client_id,
			redirect_uri: frm.doc.redirect_uri,
			scope:
				frm.doc.scope ||
				"openid profile email accounting.transactions offline_access accounting.contacts",
			state: state,
		}).toString();

	// Open authorization window
	window.open(authUrl, "_blank", "width=600,height=700,scrollbars=yes,resizable=yes");

	frappe.show_alert({
		message: __("Complete the authorization in the opened window"),
		indicator: "blue",
	});
}
