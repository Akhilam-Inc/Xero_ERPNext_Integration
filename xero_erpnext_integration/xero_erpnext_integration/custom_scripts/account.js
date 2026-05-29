function clear_xero_dashboard_indicators(frm) {
	if (!frm.dashboard?.stats_area_row) {
		return;
	}
	frm.dashboard.stats_area_row.find(".indicator-column").each(function () {
		const text = $(this).find(".indicator").text() || "";
		if (text.includes("Xero TaxType") || text.includes("Xero Report Tax Type")) {
			$(this).remove();
		}
	});
}

function render_xero_dashboard_indicators(frm) {
	if (frm.doc.account_type !== "Tax" || !frm.dashboard) {
		return;
	}
	clear_xero_dashboard_indicators(frm);
	if (frm.doc.custom_xero_tax_type) {
		frm.dashboard.add_indicator(
			__("Xero TaxType: {0}", [frm.doc.custom_xero_tax_type]),
			"green"
		);
	}
	if (frm.doc.custom_xero_report_tax_type) {
		frm.dashboard.add_indicator(
			__("Xero Report Tax Type: {0}", [frm.doc.custom_xero_report_tax_type]),
			"blue"
		);
	}
}

function refresh_xero_field_values(frm, result) {
	if (!result) {
		return;
	}
	const tax_type = result.tax_type || (result.data && result.data.TaxType);
	const report_tax_type = result.report_tax_type || (result.data && result.data.ReportTaxType);

	if (tax_type) {
		frm.set_value("custom_xero_tax_type", tax_type);
	}
	if (report_tax_type) {
		frm.set_value("custom_xero_report_tax_type", report_tax_type);
	}
	if (frm.doc.custom_send_to_xero !== 1) {
		frm.set_value("custom_send_to_xero", 1);
	}
	render_xero_dashboard_indicators(frm);
}

frappe.ui.form.on("Account", {
	refresh(frm) {
		// Only Tax accounts are relevant for Xero TaxRate sync.
		if (frm.doc.account_type !== "Tax") {
			return;
		}

		render_xero_dashboard_indicators(frm);

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
								refresh_xero_field_values(frm, r.message);
								frappe.show_alert(
									{
										message: __("Account synced successfully to Xero"),
										indicator: "green",
									},
									8
								);
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
										refresh_xero_field_values(frm, r.message);
										frappe.show_alert(
											{
												message: __("Account synced successfully to Xero"),
												indicator: "green",
											},
											8
										);
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
