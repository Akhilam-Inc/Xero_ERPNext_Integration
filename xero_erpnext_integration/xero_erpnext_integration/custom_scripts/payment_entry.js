frappe.ui.form.on('Payment Entry', {
    refresh(frm) {
        console.log("I am here")
    },
    before_submit: function(frm){
        // send_payment_to_xero(frm)
    },
   
    
    
});


function send_payment_to_xero(frm){
     frappe.call({
        method: 'xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry.create_payment',
        args:{
            doc: frm.doc.name
        },
        callback: function(r) {
            if (r.message) {
                if (r.message.status === 'success') {
                    console.log(r.message)
                    
                    frappe.show_alert({
                        title: 'Success',
                        message: r.message.message,
                        indicator: 'green'
                    })
                    frm.set_value("custom_xero_payment_id", r.message.data.PaymentID);
                    frm.set_df_property("custom_xero_payment_id", 'read_only', 1);
                    // frm.save()
                } else {
                    frappe.throw("Error creating payment in Xero");
                    
                }
            }
        }, error: function(e){
            frappe.throw("Error creating payment in Xero");

        }
        
    });
}
