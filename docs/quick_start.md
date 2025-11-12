# Quick Start

This guide walks you through a minimal end-to-end validation of the integration.

1. **Authenticate with Xero**
   - In `Xero Settings`, click `Connect to Xero` and complete the OAuth consent.
   - Ensure the status shows as connected.

2. **Sync contacts**
   - From the `Xero Settings` form, trigger the `Sync Contacts` server action.
   - Confirm that new contacts appear under Customer or Supplier masters in ERPNext.

3. **Push a sales invoice to Xero**
   - Create a `Sales Invoice` in ERPNext with a customer that originated from Xero.
   - Submit the invoice to trigger the integration hook.
   - Check Xero to verify the invoice was created.

4. **Pull payment updates**
   - Record a payment for the invoice inside Xero.
   - Run the `Sync Payments` scheduled job (or execute `bench execute xero_erpnext_integration.xero_erpnext_integration.apis.payment_entry.sync_payments`).
   - Confirm the payment entry is reflected in ERPNext.

5. **Review logs**
   - Open the `Xero API Log` DocType to review successful and failed API calls.
   - Resolve any errors before moving to production.

