# Code Structure

```
xero_erpnext_integration/
├── README.md
├── license.txt
├── pyproject.toml
├── docs/
│   ├── architecture.md
│   ├── api_reference.md
│   ├── code_structure.md
│   ├── installation.md
│   ├── overview.md
│   ├── post_installation.md
│   └── quick_start.md
├── xero_erpnext_integration/
│   ├── __init__.py
│   ├── config/
│   │   └── __init__.py
│   ├── fixtures/
│   │   ├── custom_field.json
│   │   └── property_setter.json
│   ├── hooks.py
│   ├── modules.txt
│   ├── patches.txt
│   ├── public/
│   │   ├── css/
│   │   ├── images/
│   │   │   └── akhilam-logo.svg
│   │   └── js/
│   ├── templates/
│   │   ├── __init__.py
│   │   ├── includes/
│   │   └── pages/
│   │       └── __init__.py
│   ├── www/
│   │   └── xero-help.html
│   └── xero_erpnext_integration/
│       ├── __init__.py
│       ├── apis/
│       │   ├── base.py
│       │   ├── connection.py
│       │   ├── contact.py
│       │   ├── invoice_sync.py
│       │   ├── payment_entry.py
│       │   ├── sales_invoice.py
│       │   └── webhook.py
│       ├── custom_scripts/
│       │   ├── contact.js
│       │   ├── contact.py
│       │   ├── payment_entry.js
│       │   ├── sales_invoice.js
│       │   └── sales_invoice.py
│       ├── doctype/
│       │   ├── xero_api_log/
│       │   │   ├── __init__.py
│       │   │   ├── test_xero_api_log.py
│       │   │   ├── xero_api_log.js
│       │   │   ├── xero_api_log.json
│       │   │   └── xero_api_log.py
│       │   └── xero_settings/
│       │       ├── __init__.py
│       │       ├── test_xero_settings.py
│       │       ├── xero_settings.js
│       │       ├── xero_settings.json
│       │       └── xero_settings.py
│       ├── schedulers/
│       │   └── voided_invoice_sync.py
│       ├── workspace/
│       │   └── xero_integration/
│       │       └── xero_integration.json
│       └── __pycache__/
└── .git/
```

## Key Modules

- `apis/base.py` – Shared helpers for authentication, request signing, and pagination.
- `apis/sales_invoice.py` – Handles pushing ERPNext sales invoices to Xero and reconciling responses.
- `apis/payment_entry.py` – Imports payments from Xero and pairs them with ERPNext invoice transactions.
- `apis/contact.py` – Manages bi-directional contact synchronisation.
- `schedulers/voided_invoice_sync.py` – Periodic reconciliation of voided invoice states.
- `doctype/xero_settings/` – Configuration interface for credentials, sync windows, and mappings.
- `doctype/xero_api_log/` – Persistence layer for API transaction logs.

