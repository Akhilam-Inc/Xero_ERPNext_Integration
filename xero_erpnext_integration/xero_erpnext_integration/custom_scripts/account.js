frappe.ui.form.on("Account", {
	refresh(frm) {
		// Only Tax accounts are relevant for Xero TaxRate sync.
		if (frm.doc.account_type !== "Tax") {
			return;
		}

		// Show TaxType (read-only) once it's been set so users know the mapping.
		if (frm.doc.custom_xero_tax_type) {
			frm.dashboard.add_indicator(
				__("Xero TaxType: {0}", [frm.doc.custom_xero_tax_type]),
				"green"
			);
		}

		// Manual sync button: only when sync is enabled and not yet mapped.
		if (!frm.is_new() && frm.doc.custom_send_to_xero && !frm.doc.custom_xero_tax_type) {
			frm.add_custom_button(
				__("Send to Xero"),
				function () {
					frappe.call({
						method: "xero_erpnext_integration.xero_erpnext_integration.custom_scripts.account.send_tax_account_to_xero",
						args: { doc_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Syncing Tax Rate to Xero..."),
						callback: function (r) {
							if (r.message && r.message.status === "success") {
								frappe.show_alert(
									{
										message: __("Tax Rate synced to Xero"),
										indicator: "green",
									},
									8
								);
								frm.reload_doc();
							}
						},
					});
				},
				__("Xero")
			);
		}

		// Re-sync (force update) button when already mapped.
		if (!frm.is_new() && frm.doc.custom_xero_tax_type) {
			frm.add_custom_button(
				__("Re-sync to Xero"),
				function () {
					frappe.confirm(
						__(
							"This will push the current tax_rate/name back to Xero TaxType {0}. Continue?",
							[frm.doc.custom_xero_tax_type]
						),
						function () {
							frappe.call({
								method: "xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate.create_tax_rate",
								args: {
									account_name: frm.doc.name,
									update: true,
								},
								freeze: true,
								freeze_message: __("Updating Tax Rate in Xero..."),
								callback: function (r) {
									if (r.message && r.message.status === "success") {
										frappe.show_alert(
											{
												message: __("Tax Rate updated in Xero"),
												indicator: "green",
											},
											8
										);
										frm.reload_doc();
									}
								},
							});
						}
					);
				},
				__("Xero")
			);
		}
	},

	custom_send_to_xero(frm) {
		// If the user just enabled the checkbox on a Tax account with a rate,
		// hint that saving will trigger an auto-sync.
		if (
			frm.doc.account_type === "Tax" &&
			frm.doc.custom_send_to_xero &&
			!frm.doc.custom_xero_tax_type &&
			!frm.is_new()
		) {
			frappe.show_alert(
				{
					message: __(
						"Save the account to push this Tax Rate to Xero, or use the 'Send to Xero' button."
					),
					indicator: "blue",
				},
				8
			);
		}
	},
});
