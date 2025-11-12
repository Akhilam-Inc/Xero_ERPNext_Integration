
frappe.ui.form.on('Contact', {
    refresh(frm) {

        // Make the send_to_xero field read-only if contact already exists in Xero
        if (!frm.doc.custom_contact_id) {
            if (frm.doc.custom_send_to_xero) {

                /*
                * Add custom button to send contact to Xero
                * This button will only be visible if the contact is not already synced with Xero
                * and the contact is not a new document.
                * The button will validate the account number and customer links before proceeding.
                * If the account number is not provided or no customer links are present,
                * it will show an alert message.
                */
                frm.add_custom_button("Send to Xero", function () {
                    if (!frm.doc.links.map(item => item.link_doctype === "Customer").length) {
                        frappe.show_alert({
                            title: 'Warning',
                            message: 'Please add a customer to links in Reference before sending to Xero',
                            indicator: 'orange'
                        });
                        return;
                    }

                    frappe.call({
                        method: "xero_erpnext_integration.xero_erpnext_integration.custom_scripts.contact.send_contact_to_xero",
                        args: {
                            doc_name: frm.doc.name
                        },
                        callback: function (response) {
                            if (response.message) {
                                
                                frappe.show_alert({
                                    title: 'Success',
                                    message: 'Contact sent to Xero successfully',
                                    indicator: 'green'
                                }, 10);
                                frm.set_value("custom_send_to_xero", 1);
                                frm.set_df_property("custom_send_to_xero", "read_only", true);
                                frm.set_df_property("custom_account_number", "read_only", true);
                                frm.save()
                                frm.reload_doc()
                            } else {
                                frappe.show_alert({
                                    title: 'Error',
                                    message: 'Failed to send contact to Xero',
                                    indicator: 'red'
                                });
                            }
                        }});
                });
            }
        }
    },
});
