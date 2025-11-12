import frappe
from .sales_invoice import get_specific_invoices


@frappe.whitelist()
def create_payment_from_xero(xero_invoice_id, payment_amount):
    """Create payment entry when payment is received in Xero"""
    try:
        # Find ERPNext invoice
        sales_invoice_name = frappe.db.get_value(
            "Sales Invoice", 
            {"xero_invoice_id": xero_invoice_id}, 
            "name"
        )
        
        if not sales_invoice_name:
            return {
                "status": "error",
                "message": f"No ERPNext invoice found for Xero ID: {xero_invoice_id}"
            }
        
        sales_invoice = frappe.get_doc("Sales Invoice", sales_invoice_name)
        
        # Check if already paid
        if sales_invoice.status == "Paid":
            return {
                "status": "info",
                "message": f"Invoice {sales_invoice_name} already marked as paid"
            }
        
        # Create Payment Entry
        payment_entry = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "party_type": "Customer",
            "party": sales_invoice.customer,
            "paid_amount": payment_amount,
            "received_amount": payment_amount,
            "target_exchange_rate": 1,
            "reference_no": f"Xero-{xero_invoice_id}",
            "reference_date": frappe.utils.today(),
            "paid_to": get_default_receivable_account(),
            "paid_from": get_default_cash_account(),
            "references": [{
                "reference_doctype": "Sales Invoice",
                "reference_name": sales_invoice_name,
                "allocated_amount": payment_amount
            }]
        })
        
        payment_entry.insert(ignore_permissions=True)
        payment_entry.submit()
        
        return {
            "status": "success",
            "message": f"Payment entry created: {payment_entry.name}",
            "payment_entry": payment_entry.name
        }
        
    except Exception as e:
        frappe.logger().error(f"Failed to create payment for Xero invoice {xero_invoice_id}: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

def get_default_receivable_account():
    """Get default receivable account"""
    company = frappe.defaults.get_user_default("Company")
    return frappe.db.get_value("Company", company, "default_receivable_account")

def get_default_cash_account():
    """Get default cash account"""  
    company = frappe.defaults.get_user_default("Company")
    return frappe.db.get_value("Company", company, "default_cash_account")


