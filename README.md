# Xero ERPNext Integration

## Overview

The Xero ERPNext Integration app keeps accounting data consistent across Xero and ERPNext. It offers guided setup, secure OAuth 2.0 connectivity, and resilient synchronisation jobs so finance and operations teams stay aligned.

## Features

- Two-way synchronisation for contacts, sales invoices, and payments
- OAuth 2.0 authentication with token refresh handled automatically
- Scheduled jobs plus on-demand actions for backfilling data
- Webhook ingestion for near real-time updates from Xero
- Detailed API logging via the `Xero API Log` DocType for monitoring and audits

## Installation

```bash
cd /path/to/your/frappe-bench
bench get-app https://github.com/Akhilam-Inc/Xero_ERPNext_Integration.git
bench --site <your-site-name> install-app xero_erpnext_integration
bench migrate
```

See `docs/installation.md` for prerequisites and verification steps.

## Post-Installation Setup

- Register a connected app in the Xero developer portal and capture credentials.
- Complete the OAuth handshake inside `Xero Settings`.
- Map ERPNext accounts, taxes, and items to the corresponding Xero records.
- Enable the scheduler events you need (invoices, payments, voided invoices).
- Confirm permissions and test with a non-production Xero organisation first.

Additional guidance is available in `docs/post_installation.md`.

## Quick Start

1. Connect to Xero through the `Xero Settings` DocType.
2. Trigger a contact sync to import reference data.
3. Create and submit a sales invoice in ERPNext and verify it appears in Xero.
4. Record a payment in Xero and pull it into ERPNext via the payment sync.
5. Review `Xero API Log` for success or failure entries.

Follow the step-by-step walkthrough in `docs/quick_start.md`.

## Documentation

- `docs/overview.md`
- `docs/installation.md`
- `docs/post_installation.md`
- `docs/quick_start.md`
- `docs/api_reference.md`
- `docs/architecture.md`
- `docs/code_structure.md`

## API Reference

Whitelisted Frappe methods and webhook endpoints are documented in `docs/api_reference.md`. Each entry includes the REST path, expected arguments, and authentication requirements for integrating with external systems or custom ERPNext scripts.

## Architecture

Core integration logic lives under `xero_erpnext_integration/apis/`, with schedulers driving recurring jobs and DocTypes handling configuration and logging. Consult `docs/architecture.md` for a deeper dive into components, data flow, and error handling.

## Code Structure

```
xero_erpnext_integration/
├── README.md
├── license.txt
├── pyproject.toml
├── docs/
│   ├── architecture.md
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

Key modules:

- `apis/base.py` for shared API helpers
- `apis/sales_invoice.py` for invoice sync workflows
- `apis/payment_entry.py` for payment import and reconciliation
- `apis/contact.py` for bidirectional contact sync
- `schedulers/voided_invoice_sync.py` for voided invoice catch-up jobs

## License

```
MIT License

Copyright (c) 2025 Akhilam Inc

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

 Made with ❤️ by [Akhilam Inc](https://akhilaminc.com).
