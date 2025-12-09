frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		console.log(frm.doc.workflow_state);
		if (!frm.doc.custom_contact_id && frm.doc.customer && frm.doc.contact_person) {
			frm.add_custom_button(__("Sync Contact in Xero"), function () {
				if (frm.doc.customer && frm.doc.contact_person) {
					frappe.call({
						method: "xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.fetch_xero_contacts",
						args: {
							contact_person: frm.doc.contact_person,
						},
						callback: function (r) {
							if (r.message && r.message.length > 0) {
								show_contact_mapping_dialog(
									frm,
									r.message,
									frm.doc.contact_person
								);
							} else {
								show_create_contact_dialog(frm, frm.doc.contact_person);
							}
						},
					});
				}
			});
		}
		if (
			!frm.doc.custom_xero_invoice_number &&
			frm.doc.docstatus == 1 &&
			!frm.doc.custom_do_not_sync_to_xero
		) {
			frm.add_custom_button(
				__("Sync Invoice in Xero"),
				function () {
					frappe.call({
						method: "xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.create_invoice",
						args: {
							doc: frm.doc.name,
							sync_to_xero: false,
						},
						callback: function (r) {
							if (r.message) {
								if (r.message.status === "success") {
									// Use frappe.db.set_value to update only the specific field without triggering save
									frappe.db.set_value(
										"Sales Invoice",
										frm.doc.name,
										"custom_xero_invoice_number",
										r.message.data.InvoiceID,
										function () {
											frappe.msgprint(
												__("Invoice created successfully in Xero")
											);
											frm.reload_doc();
										}
									);
								} else {
									frappe.msgprint(__("Failed to create invoice in Xero"));
								}
							}
						},
					});
				},
				__("Action")
			);
		} else if (frm.doc.custom_do_not_sync_to_xero && frm.doc.docstatus == 1) {
			frm.add_custom_button(
				__("Enable Xero Sync"),
				function () {
					frappe.db.set_value(
						"Sales Invoice",
						frm.doc.name,
						"custom_do_not_sync_to_xero",
						0,
						function () {
							frappe.msgprint(
								__("Xero sync enabled for this invoice. You can now sync to Xero.")
							);
							frm.reload_doc();
						}
					);
				},
				__("Action")
			);
		}
	},
	before_workflow_action: async (frm) => {
		if (frm.doc.workflow_state === "Sync to Xero") {
			let promise = new Promise((resolve, reject) => {
				console.log(frm.doc.workflow_state);
				//    sync_to_xero_workflow_action(frm.doc);
			});
			frappe.dom.unfreeze();
			await promise.catch(() => {
				throw "";
			});
			frm.reload_doc();
		}
	},

	customer(frm) {
		// Also trigger when customer is changed
		if (frm.doc.customer) {
			frappe.call({
				method: "xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.get_customer_contact_id",
				args: {
					customer: frm.doc.customer,
				},
				callback: function (r) {
					if (r.message) {
						let contact = r.message;
						// Set the custom_contact_id field in Sales Invoice
						frm.set_value("custom_contact_id", r.message);
					}
				},
			});
		} else {
			// Clear the field if no customer selected
			frm.set_value("custom_contact_id", "");
		}
	},
	validate(frm) {
		if (frm.doc.customer) {
			frappe.call({
				method: "xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.get_customer_contact_id",
				args: {
					customer: frm.doc.customer,
				},
				callback: function (r) {
					if (r.message) {
						let contact = r.message;
						// Set the custom_contact_id field in Sales Invoice
						frm.set_value("custom_contact_id", r.message);
					}
				},
			});
		} else {
			// Clear the field if no customer selected
			frm.set_value("custom_contact_id", "");
		}
	},
});

function show_contact_mapping_dialog(frm, xero_contacts, contact_person) {
	let d = new frappe.ui.Dialog({
		title: __("Map Contact to Xero"),
		fields: [
			{
				fieldname: "contact_person",
				fieldtype: "Data",
				label: __("Contact Person"),
				default: contact_person,
				read_only: 1,
			},
			{
				fieldname: "xero_contacts",
				fieldtype: "HTML",
				label: __("Similar Xero Contacts"),
			},
		],
		primary_action_label: __("Create New Contact"),
		primary_action: function () {
			d.hide();
			create_contact_in_xero(frm, contact_person);
		},
		secondary_action_label: __("Close"),
		secondary_action: function () {
			d.hide();
		},
	});

	let html = '<div style="max-height: 300px; overflow-y: auto;">';
	xero_contacts.forEach(function (contact, index) {
		html += `
            <div style="border: 1px solid #ddd; padding: 10px; margin: 5px 0; border-radius: 4px;">
                <div><strong>${contact.Name || ""}</strong></div>
                <div>Email: ${contact.EmailAddress || "-"}</div>
                <div>Phone: ${
					contact.Phones && contact.Phones[0] ? contact.Phones[0].PhoneNumber : "-"
				}</div>
                <button class="btn btn-primary btn-sm map-contact-btn"
                        data-contact-id="${contact.ContactID}"
                        data-contact-person="${frm.doc.contact_person}"
                        data-sales-invoice="${frm.doc.name}"
                        style="margin-top: 5px;">
                    Map Contact
                </button>
            </div>
        `;
	});
	html += "</div>";

	d.fields_dict.xero_contacts.$wrapper.html(html);

	// Add click event handlers
	d.fields_dict.xero_contacts.$wrapper.find(".map-contact-btn").on("click", function () {
		const contactId = $(this).data("contact-id");
		const contactPerson = $(this).data("contact-person");
		const salesInvoice = $(this).data("sales-invoice");
		map_contact(contactId, contactPerson, salesInvoice);
		d.hide();
	});
	d.show();
}

function map_contact(contact_id, contact_person, sales_invoice) {
	frappe.call({
		method: "xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.map_contact_to_xero",
		args: {
			contact_id: contact_id,
			contact_person: contact_person,
			sales_invoice: sales_invoice,
		},
		callback: function (r) {
			if (r.message) {
				frappe.msgprint(__("Contact mapped successfully"));
				cur_frm.reload_doc();
			} else {
				frappe.msgprint(__("Failed to map contact"));
			}
		},
	});
}

function show_create_contact_dialog(frm, contact_person) {
	let d = new frappe.ui.Dialog({
		title: __("Create Contact in Xero"),
		fields: [
			{
				fieldname: "message",
				fieldtype: "HTML",
				label: __("Message"),
			},
		],
		primary_action_label: __("Create Contact"),
		primary_action: function () {
			create_contact_in_xero(frm, contact_person);
			d.hide();
		},
		secondary_action_label: __("Cancel"),
		secondary_action: function () {
			d.hide();
		},
	});

	let html = `
        <div style="padding: 10px;">
            <p><strong>No similar contacts found in Xero for:</strong> ${contact_person}</p>
            <p>Would you like to create a new contact in Xero using the details from ERPNext?</p>
        </div>
    `;

	d.fields_dict.message.$wrapper.html(html);
	d.show();
}

function create_contact_in_xero(frm, contact_person) {
	frappe.call({
		method: "xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.create_contact_and_map",
		args: {
			contact_person: contact_person,
			sales_invoice: frm.doc.name,
		},
		callback: function (r) {
			if (r.message && r.message.status === "success") {
				frappe.msgprint(__("Contact created successfully in Xero"));
				cur_frm.reload_doc();
			} else {
				frappe.msgprint(__("Failed to create contact in Xero"));
			}
		},
	});
}

// Function to handle workflow action "Sync to Xero"
function sync_to_xero_workflow_action(doc) {
	frappe.call({
		method: "xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.create_invoice",
		args: {
			doc: doc.name,
			sync_to_xero: false,
		},
		callback: function (r) {
			if (r.message) {
				if (r.message.status === "success") {
					// Update the Xero invoice number
					frappe.db.set_value(
						"Sales Invoice",
						doc.name,
						"custom_xero_invoice_number",
						r.message.data.InvoiceID,
						function () {
							frappe.msgprint(__("Invoice synced successfully to Xero"));
							// Reload the form to reflect changes
							if (cur_frm) {
								cur_frm.reload_doc();
							}
						}
					);
				} else {
					frappe.msgprint(__("Failed to sync invoice to Xero"));
				}
			}
		},
	});
}

// Make the function globally available for workflow actions
// window.sync_to_xero_workflow_action = sync_to_xero_workflow_action;
