frappe.listview_settings["Account"] = {
	onload(listview) {
		listview.page.add_inner_button(
			__("Sync selected Tax Rates to Xero"),
			async () => {
				const selected = listview.get_checked_items(true);
				if (!selected || !selected.length) {
					frappe.msgprint(__("Select at least one Tax Account."));
					return;
				}

				frappe.dom.freeze(__("Syncing selected Tax Rates to Xero..."));
				try {
					const r = await frappe.call({
						method: "xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate.sync_selected_tax_rates",
						args: { accounts: selected },
					});

					const res = r && r.message ? r.message : {};
					const created = res.created || [];
					const skipped = res.skipped || [];
					const failed = res.failed || [];

					let msg = __(
						"Xero TaxRate sync complete. Created: {0}, Skipped: {1}, Failed: {2}",
						[created.length, skipped.length, failed.length]
					);

					if (created.length) {
						msg +=
							"<br><br><strong>" +
							__("Created") +
							"</strong><br>" +
							created
								.slice(0, 20)
								.map(
									(x) =>
										`${frappe.utils.escape_html(
											x.name
										)} → ${frappe.utils.escape_html(x.tax_type || "")}`
								)
								.join("<br>");
						if (created.length > 20) msg += "<br>...";
					}

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
						title: __("Sync Tax Rates to Xero"),
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
			__("Pull Tax Rates from Xero"),
			() => open_pull_tax_rates_dialog(listview),
			__("Xero Action")
		);
	},
};

function open_pull_tax_rates_dialog(listview) {
	const d = new frappe.ui.Dialog({
		title: __("Pull Tax Rates from Xero"),
		fields: [
			{
				fieldname: "company",
				fieldtype: "Link",
				options: "Company",
				label: __("Company (for new accounts)"),
				reqd: 1,
				default: frappe.defaults.get_user_default("Company"),
			},
			{
				fieldname: "parent_account",
				fieldtype: "Link",
				options: "Account",
				label: __("Parent Account (group)"),
				description: __(
					"New Tax accounts will be created under this group. Leave blank to auto-pick a Tax/Duties group."
				),
				get_query: function () {
					const company = d.get_value("company");
					return {
						filters: {
							is_group: 1,
							company: company || undefined,
							root_type: "Liability",
						},
					};
				},
			},
			{
				fieldname: "info",
				fieldtype: "HTML",
				options: `<div class="text-muted small">${__(
					"This will fetch all TaxRates from Xero. Matching ERPNext Tax accounts (by name) will be back-filled with the Xero TaxType. Any TaxRate without a matching account will be CREATED as a new Tax account under the selected company / parent."
				)}</div>`,
			},
		],
		primary_action_label: __("Pull from Xero"),
		primary_action: async (values) => {
			d.hide();
			frappe.dom.freeze(__("Pulling Tax Rates from Xero..."));
			try {
				const r = await frappe.call({
					method: "xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate.pull_tax_rates_from_xero",
					args: {
						company: values.company,
						parent_account: values.parent_account || null,
					},
				});
				const res = (r && r.message) || {};
				render_pull_result(res);
				listview.refresh();
			} finally {
				frappe.dom.unfreeze();
			}
		},
	});
	d.show();
}

function render_pull_result(res) {
	const created = res.created || [];
	const mapped = res.mapped || [];
	const skipped = res.skipped || [];
	const failed = res.failed || [];

	let msg = __("Pull complete. Created: {0}, Mapped: {1}, Skipped: {2}, Failed: {3}", [
		created.length,
		mapped.length,
		skipped.length,
		failed.length,
	]);
	if (res.parent_account) {
		msg += `<br><br><em>${__("New accounts placed under")}: ${frappe.utils.escape_html(
			res.parent_account
		)} (${frappe.utils.escape_html(res.company || "")})</em>`;
	}

	const section = (title, rows, fmt) => {
		if (!rows.length) return "";
		const items = rows
			.slice(0, 20)
			.map((x) => fmt(x))
			.join("<br>");
		const more = rows.length > 20 ? "<br>..." : "";
		return `<br><br><strong>${title}</strong><br>${items}${more}`;
	};

	msg += section(
		__("Created"),
		created,
		(x) =>
			`${frappe.utils.escape_html(x.account)} ← ${frappe.utils.escape_html(
				x.xero_name || ""
			)} (${frappe.utils.escape_html(x.tax_type || "")})`
	);
	msg += section(
		__("Mapped"),
		mapped,
		(x) =>
			`${frappe.utils.escape_html(x.account)} → ${frappe.utils.escape_html(
				x.tax_type || ""
			)}`
	);
	msg += section(
		__("Skipped"),
		skipped,
		(x) =>
			`${frappe.utils.escape_html(
				x.xero_name || x.account || ""
			)}: ${frappe.utils.escape_html(x.reason || "")}`
	);
	msg += section(
		__("Failed"),
		failed,
		(x) =>
			`${frappe.utils.escape_html(
				x.xero_name || x.account || ""
			)}: ${frappe.utils.escape_html(x.error || "")}`
	);

	frappe.msgprint({
		title: __("Pull Tax Rates from Xero"),
		message: msg,
		indicator: failed.length ? "orange" : "green",
	});
}
