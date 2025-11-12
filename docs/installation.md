# Installation

## Prerequisites

- Bench with a running ERPNext v15 environment
- Xero organisation with API (OAuth 2.0) access
- Access to a user that can install custom apps on the bench

## Steps

```bash
cd /path/to/your/frappe-bench
bench get-app xero_erpnext_integration https://github.com/<your-org>/xero_erpnext_integration.git
bench --site <your-site-name> install-app xero_erpnext_integration
bench migrate
```

> Replace `<your-org>` and `<your-site-name>` with the correct values for your environment.

## Verification

1. Log into the Desk of the target site.
2. Search for `Xero Settings` to ensure the DocType is available.
3. Review the bench logs to confirm no installation errors were raised.

