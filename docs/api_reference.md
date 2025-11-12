# API Reference

This integration exposes a set of whitelisted Frappe methods that can be called from the Desk, REST API, or server-side scripts. Unless noted otherwise, all endpoints require an authenticated ERPNext user session with access to the relevant DocTypes.

## REST Endpoints

| Endpoint | Method | Description | Auth |
| --- | --- | --- | --- |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.connection.authorize` | POST | Exchanges the stored authorization code for OAuth tokens and validates the connection. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.base.get_xero_client` | GET | Returns a configured Xero API client wrapper (primarily for internal use). | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.contact.get_xero_contacts` | GET | Fetches contacts from Xero. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.contact.create_contact` | POST | Pushes an ERPNext `Contact` to Xero. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.sync_invoice_payments` | POST | Pulls payments from Xero for open ERPNext sales invoices. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.create_invoice` | POST | Creates or updates a Xero invoice from an ERPNext `Sales Invoice`. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.fetch_xero_contacts` | GET | Returns Xero contacts with names similar to the provided ERPNext contact. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.create_contact_and_map` | POST | Creates a Xero contact based on an ERPNext contact and maps it to a sales invoice. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.map_contact_to_xero` | POST | Persists an existing Xero `ContactID` on ERPNext contact and invoice records. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.cancel_invoice_in_xero` | POST | Voids a Xero invoice by ID. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.get_customer_contact_id` | GET | Returns the stored Xero `ContactID` for a given ERPNext customer. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry.create_payment` | POST | Creates a payment in Xero for the referenced ERPNext payment entry. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry.get_account_code` | GET | Resolves the Xero account code mapped to an ERPNext account. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry.get_customer_contact_id` | GET | Returns the Xero `ContactID` bound to the customer linked to a payment entry. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry.sync_payment_to_xero` | POST | Convenience wrapper to push a payment entry to Xero. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.invoice_sync.create_payment_from_xero` | POST | Creates an ERPNext `Payment Entry` based on Xero payment information. | User |
| `/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.webhook.webhook` | GET/POST | Xero webhook entry point. GET answers the intent-to-receive challenge; POST processes invoice events. | Guest (signature required) |

> The webhook endpoint is publicly accessible but validates HMAC signatures using the secret stored in `Xero Settings`.

## Usage Examples

### Calling from the REST API

```bash
curl -X POST \
  https://<your-site>/api/method/xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.create_invoice \
  -H "Authorization: token <api-key>:<api-secret>" \
  -H "Content-Type: application/json" \
  -d '{"doc": "SINV-0001"}'
```

### Calling from Client Scripts

```javascript
frappe.call({
  method: "xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry.sync_payment_to_xero",
  args: { payment_entry_name: cur_frm.doc.name },
  callback(r) {
    if (!r.exc) {
      frappe.msgprint(r.message || "Sync request sent to Xero");
    }
  }
});
```

### Server-Side Helpers

Some workflows are exposed as convenience wrappers for `bench execute`:

```bash
bench execute xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.sync_invoice_payments
bench execute xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry.sync_payment_to_xero --kwargs "{'payment_entry_name': 'PAY-0001'}"
```

## Notes

- Most endpoints expect prerequisite configuration in `Xero Settings` (client credentials, tenant details, account mappings).
- Responses are JSON-formatted dictionaries containing `status`, `message`, and optional `data` payloads for downstream handling.
- Use the `Xero API Log` DocType to audit requests made via these endpoints.

