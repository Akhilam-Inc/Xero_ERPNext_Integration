frappe.ui.form.on('Sales Invoice', {
    refresh(frm) {
        add_xero_buttons(frm);
        set_status_indicator(frm);
        if(frm.doc.status != 'Draft'){
            frm.set_df_property('custom_do_not_sync_to_xero', 'read_only', 1);
        }
    },


    before_workflow_action: async(frm) => {
        if (frm.doc.workflow_state === 'Draft' && frm.doc.custom_contact_id && !frm.doc.custom_do_not_sync_to_xero) {
            sync_to_xero_workflow_action(frm.doc, false);
            frm.reload_doc();
        }
        else if (frm.doc.workflow_state === 'Synced to Xero' && frm.doc.custom_xero_invoice_number) {
            sync_to_xero_workflow_action(frm.doc, true);
            frm.reload_doc();
        }
    },

    after_workflow_action: async(frm) => {
        if (!frm.doc.custom_contact_id && frm.doc.workflow_state === 'Draft' && !frm.doc.custom_do_not_sync_to_xero) {
            frappe.msgprint(__('Please map the contact to Xero first'));
        }
    },

    customer(frm) {
        update_customer_contact_id(frm);
    },

    after_save(frm) {
        if (frm.doc.customer && frm.doc.custom_do_not_sync_to_xero == 0) {
            update_customer_contact_id(frm, true);
        }

        if (frm.doc.workflow_state === 'Synced to Xero' && frm.doc.custom_xero_invoice_number) {
            sync_to_xero_workflow_action(frm.doc, true);
            frm.reload_doc();
        }
    }
});

// ---------------- Helper Functions ----------------

function add_xero_buttons(frm) {
    const canSyncContact = !frm.is_new() && frm.doc.customer && frm.doc.contact_person && !frm.doc.custom_do_not_sync_to_xero && !frm.doc.custom_contact_id;
    const canSyncInvoice = !frm.doc.custom_xero_invoice_number && frm.doc.docstatus === 1 && !frm.doc.custom_do_not_sync_to_xero;
    const canEnableSync = frm.doc.custom_do_not_sync_to_xero && frm.doc.docstatus === 1;

    if (canSyncContact) {
        frm.add_custom_button(__('Sync Contact in Xero'), () => fetch_xero_contacts(frm));
    }

    if (canSyncInvoice) {
        frm.add_custom_button(__('Sync Invoice in Xero'), () => create_invoice_in_xero(frm), __("Action"));
    }
    else if (canEnableSync) {
        frm.add_custom_button(__('Enable Xero Sync'), () => toggle_xero_sync(frm, false), __("Action"));
    }
}

function add_status_button(frm, label, color) {
    frm.add_custom_button(__(label), function () {})
        .css('background-color', color)
        .css('color', 'white');
}

function fetch_xero_contacts(frm) {
    frappe.call({
        method: 'xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.fetch_xero_contacts',
        args: { contact_person: frm.doc.contact_person },
        callback(r) {
            if (r.message && r.message.length > 0) {
                show_contact_mapping_dialog(frm, r.message, frm.doc.contact_person);
            } else {
                show_create_contact_dialog(frm, frm.doc.contact_person);
            }
        }
    });
}

function create_invoice_in_xero(frm) {
    if(frm.doc.custom_contact_id){
        frappe.call({
            method: 'xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.create_invoice',
            args: { doc: frm.doc.name, sync_to_xero: false },
            callback(r) {
                if (r.message) {
                    if (r.message.status === 'success') {
                        frappe.db.set_value('Sales Invoice', frm.doc.name, 'custom_xero_invoice_number', r.message.data.InvoiceID, () => {
                            frappe.msgprint(__('Invoice created successfully in Xero'));
                            frm.reload_doc();
                        });
                    } else {
                        frappe.msgprint(__('Failed to create invoice in Xero'));
                    }
                }
            }
        });
    }else{
        frappe.msgprint(__('Please map the contact to Xero first'));
    }
}

function set_status_indicator(frm){
    const statusConfig = {
        'Draft': {
            color: 'red',
            label: __(`${frm.doc.status} - Draft`)
        },
        'Submitted': {
            color: 'blue',
            label: __(`${frm.doc.status} - Submitted`)
        },
        'Synced to Xero': {
            color: 'green',
            label: __(`${frm.doc.status} - Synced to Xero`)
        }
    };
    if(frm.doc.workflow_state){
        frm.page.set_indicator(
            statusConfig[frm.doc.workflow_state].label,
            statusConfig[frm.doc.workflow_state].color,
        );
    }
}

function toggle_xero_sync(frm, disable) {
    frappe.db.set_value('Sales Invoice', frm.doc.name, 'custom_do_not_sync_to_xero', disable ? 1 : 0, () => {
        frappe.msgprint(
            disable
                ? __('Xero sync disabled for this invoice.')
                : __('Xero sync enabled for this invoice. You can now sync to Xero.')
        );
        frm.reload_doc();
    });
}

function update_customer_contact_id(frm, autoSave = false) {
    if (frm.doc.customer) {
        frappe.call({
            method: 'xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.get_customer_contact_id',
            args: { customer: frm.doc.customer },
            callback(r) {
                if (r.message) {
                    frm.set_value('custom_contact_id', r.message);
                    if (autoSave) frm.save();
                } else {
                    frm.set_value('custom_contact_id', '');
                    frm.set_value('workflow_state', 'Draft');
                    if (autoSave) frm.save();
                }
            }
        });
    } else {
        frm.set_value('custom_contact_id', '');
    }
}


function show_contact_mapping_dialog(frm, xero_contacts, contact_person) {
    let d = new frappe.ui.Dialog({
        title: __('Map Contact to Xero'),
        fields: [
            {
                fieldname: 'contact_person',
                fieldtype: 'Data',
                label: __('Contact Person'),
                default: contact_person,
                read_only: 1
            },
            {
                fieldname: 'xero_contacts',
                fieldtype: 'HTML',
                label: __('Similar Xero Contacts')
            }
        ],
        primary_action_label: __('Create New Contact'),
        primary_action: function() {
            d.hide();
            create_contact_in_xero(frm, contact_person);
        },
        secondary_action_label: __('Close'),
        secondary_action: function() {
            d.hide();
        }
    });

    let html = '<div style="max-height: 300px; overflow-y: auto;">';
    xero_contacts.forEach(function(contact, index) {
        html += `
            <div style="border: 1px solid #ddd; padding: 10px; margin: 5px 0; border-radius: 4px;">
                <div><strong>${contact.Name || ''}</strong></div>
                <div>Email: ${contact.EmailAddress || '-'}</div>
                <div>Phone: ${contact.Phones && contact.Phones[0] ? contact.Phones[0].PhoneNumber : '-'}</div>
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
    html += '</div>';

    d.fields_dict.xero_contacts.$wrapper.html(html);

    // Add click event handlers
    d.fields_dict.xero_contacts.$wrapper.find('.map-contact-btn').on('click', function() {
        const contactId = $(this).data('contact-id');
        const contactPerson = $(this).data('contact-person');
        const salesInvoice = $(this).data('sales-invoice');
        map_contact(contactId, contactPerson, salesInvoice);
        d.hide();
    });
    d.show();
}

function map_contact(contact_id, contact_person, sales_invoice) {
    frappe.call({
        method: 'xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.map_contact_to_xero',
        args: {
            contact_id: contact_id,
            contact_person: contact_person,
            sales_invoice: sales_invoice
        },
        callback: function(r) {
            if (r.message) {
                frappe.msgprint(__('Contact mapped successfully'));
                cur_frm.reload_doc();
            } else {
                frappe.msgprint(__('Failed to map contact'));
            }
        }
    });
}

function show_create_contact_dialog(frm, contact_person) {
    let d = new frappe.ui.Dialog({
        title: __('Create Contact in Xero'),
        fields: [
            {
                fieldname: 'message',
                fieldtype: 'HTML',
                label: __('Message')
            }
        ],
        primary_action_label: __('Create Contact'),
        primary_action: function() {
            create_contact_in_xero(frm, contact_person);
            d.hide();
        },
        secondary_action_label: __('Cancel'),
        secondary_action: function() {
            d.hide();
        }
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
        method: 'xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.create_contact_and_map',
        args: {
            contact_person: contact_person,
            sales_invoice: frm.doc.name
        },
        callback: function(r) {
            if (r.message && r.message.status === 'success') {
                frappe.msgprint(__('Contact created successfully in Xero'));
                cur_frm.reload_doc();
            } else {
                frappe.msgprint(__('Failed to create contact in Xero'));
            }
        }
    });
}

function sync_to_xero_workflow_action(doc, update_invoice=false) {
    frappe.call({
        method: 'xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.create_invoice',
        args: {
            doc: doc.name,
            update: update_invoice
        },
        callback: function(r) {
            if (r.message) {
                if(r.message.status === 'success' && !doc.custom_xero_invoice_number){
                    // Update the Xero invoice number
                    frappe.db.set_value('Sales Invoice', doc.name, 'custom_xero_invoice_number', r.message.data.InvoiceID, function() {
                        frappe.msgprint(__('Invoice synced successfully to Xero')); // Reload the form to reflect changes
                        if (cur_frm) {
                            cur_frm.reload_doc();
                        }
                    } );
                } else if(r.message.status === 'success' && doc.custom_xero_invoice_number){
                    frappe.msgprint(__('Invoice Updated successfully in Xero'));
                } else {
                    frappe.msgprint(__('Failed to sync invoice to Xero'));
                }
            }
        }
    });
}
