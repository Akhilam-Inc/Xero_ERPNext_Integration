frappe.listview_settings["Sales Invoice"] = {
	add_fields: [
		"status",
		"workflow_state",
		"docstatus",
		"is_return",
		"custom_xero_invoice_number",
		"custom_xero_credit_note_id",
		"custom_do_not_sync_to_xero",
	],

	get_indicator(doc) {
		// Mirrors the form-view indicator: "<status> - <Xero workflow state>".
		const is_synced = !!(
			doc.custom_xero_invoice_number ||
			doc.custom_xero_credit_note_id ||
			doc.workflow_state === "Synced to Xero"
		);

		if (is_synced) {
			return [
				doc.status + " - " + __("Synced to Xero"),
				"green",
				"workflow_state,=,Synced to Xero|custom_xero_invoice_number,is,set|custom_xero_credit_note_id,is,set",
			];
		}
		if (doc.workflow_state === "Submitted" || doc.docstatus === 1) {
			return [doc.status + " - " + __("Submitted"), "blue", "workflow_state,=,Submitted"];
		}
		return [doc.status + " - " + __("Draft"), "red", "workflow_state,=,Draft"];
	},

	onload(listview) {
		listview.page.add_inner_button(
			__("Sync selected to Xero"),
			async () => {
				const selected = listview.get_checked_items(true);
				if (!selected || !selected.length) {
					frappe.msgprint(__("Select at least one Sales Invoice."));
					return;
				}

				frappe.dom.freeze(__("Syncing selected invoices to Xero..."));
				try {
					const r = await frappe.call({
						method: "xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.sync_selected_invoices",
						args: { invoices: selected },
					});

					const res = r && r.message ? r.message : {};
					const created = res.created || [];
					const skipped = res.skipped || [];
					const failed = res.failed || [];

					let msg = __("Xero sync complete. Created: {0}, Skipped: {1}, Failed: {2}", [
						created.length,
						skipped.length,
						failed.length,
					]);

					if (skipped.length) {
						msg +=
							"<br><br><strong>" +
							__("Skipped") +
							"</strong><br>" +
							skipped
								.slice(0, 20)
								.map(
									(x) =>
										`${frappe.utils.escape_html(
											x.name
										)}: ${frappe.utils.escape_html(x.reason)}`
								)
								.join("<br>");
						if (skipped.length > 20) msg += "<br>...";
					}

					if (failed.length) {
						msg +=
							"<br><br><strong>" +
							__("Failed") +
							"</strong><br>" +
							failed
								.slice(0, 20)
								.map(
									(x) =>
										`${frappe.utils.escape_html(
											x.name
										)}: ${frappe.utils.escape_html(x.error)}`
								)
								.join("<br>");
						if (failed.length > 20) msg += "<br>...";
					}

					frappe.msgprint({
						title: __("Sync to Xero"),
						message: msg,
						indicator: failed.length ? "orange" : "green",
					});

					listview.refresh();
				} finally {
					frappe.dom.unfreeze();
				}
			},
			__("Xero Action")
		);

		listview.page.add_inner_button(
			__("Sync selected returns to Xero"),
			async () => {
				const selected = listview.get_checked_items(true);
				if (!selected || !selected.length) {
					frappe.msgprint(__("Select at least one Sales Invoice Return."));
					return;
				}

				frappe.dom.freeze(__("Syncing selected returns to Xero as Credit Notes..."));
				try {
					const r = await frappe.call({
						method: "xero_erpnext_integration.xero_erpnext_integration.apis.credit_note.sync_selected_sales_returns",
						args: { invoices: selected },
					});

					const res = r && r.message ? r.message : {};
					const created = res.created || [];
					const skipped = res.skipped || [];
					const failed = res.failed || [];

					let msg = __(
						"Credit Note sync complete. Created: {0}, Skipped: {1}, Failed: {2}",
						[created.length, skipped.length, failed.length]
					);

					if (skipped.length) {
						msg +=
							"<br><br><strong>" +
							__("Skipped") +
							"</strong><br>" +
							skipped
								.slice(0, 20)
								.map(
									(x) =>
										`${frappe.utils.escape_html(
											x.name
										)}: ${frappe.utils.escape_html(x.reason)}`
								)
								.join("<br>");
						if (skipped.length > 20) msg += "<br>...";
					}

					if (failed.length) {
						msg +=
							"<br><br><strong>" +
							__("Failed") +
							"</strong><br>" +
							failed
								.slice(0, 20)
								.map(
									(x) =>
										`${frappe.utils.escape_html(
											x.name
										)}: ${frappe.utils.escape_html(x.error)}`
								)
								.join("<br>");
						if (failed.length > 20) msg += "<br>...";
					}

					frappe.msgprint({
						title: __("Sync Credit Notes to Xero"),
						message: msg,
						indicator: failed.length ? "orange" : "green",
					});

					listview.refresh();
				} finally {
					frappe.dom.unfreeze();
				}
			},
			__("Xero Action")
		);
	},
};
