# Architecture

The integration is organised into clear layers so that synchronisation logic remains maintainable.

## High-Level Components

- **API Layer (`xero_erpnext_integration/apis/`)**  
  Contains the modules that orchestrate communication with Xero and ERPNext. Each domain (contacts, sales invoices, payments) has its own module with dedicated sync routines.

- **Webhooks (`apis/webhook.py`)**  
  Listens for incoming webhooks from Xero and queues the corresponding jobs inside ERPNext.

- **Schedulers (`schedulers/`)**  
  Defines cron-like routines that drive periodic syncs and catch-up tasks for invoices, payments, and voided transactions.

- **DocTypes (`doctype/`)**  
  Stores configuration and logging data, most notably `Xero Settings` and `Xero API Log`.

- **Custom Scripts (`custom_scripts/`)**  
  Extends ERPNext client-side behaviour to expose controls for manual syncs.

## Data Flow

1. User or scheduler triggers a sync operation.
2. The relevant API module composes requests using credentials from `Xero Settings`.
3. Responses are processed, transformed, and written into ERPNext DocTypes.
4. Each API call is logged in `Xero API Log` for auditing and troubleshooting.

## Error Handling

- Exceptions bubble up to the job queue and are persisted in `Xero API Log`.
- Retries can be configured at the scheduler level.
- Validation guards ensure incomplete documents are not pushed to Xero.

