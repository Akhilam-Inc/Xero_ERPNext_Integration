"""
Sync ERPNext Tax Accounts to Xero TaxRates.

An ERPNext Account with `account_type = "Tax"` and the custom flag
`custom_send_to_xero` enabled can be pushed to Xero. We store the Xero-assigned
`TaxType` code on the Account in `custom_xero_tax_type`; once set we use it as
the per-line TaxType on Sales Invoice and Credit Note line items so Xero
calculates tax against the correct rate.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from .base import get_xero_client

# Xero ReportTaxType values we use by default. Users with non-standard regional
# requirements can pre-populate `custom_xero_report_tax_type` on the account.
DEFAULT_SALES_REPORT_TAX_TYPE = "OUTPUT"
DEFAULT_PURCHASE_REPORT_TAX_TYPE = "INPUT"


def _resolve_report_tax_type(account) -> str:
	"""Pick the Xero ReportTaxType for an Account.

	Priority:
	1. Explicit `custom_xero_report_tax_type` set on the account
	2. INPUT for purchase-side tax accounts (root_type=Liability with parent
	   containing 'purchase' OR `tax_rate` source identifies as purchase),
	   OUTPUT otherwise.
	"""
	explicit = account.get("custom_xero_report_tax_type")
	if explicit:
		return explicit

	# Heuristic: accounts whose name contains "purchase"/"input" map to INPUT,
	# everything else defaults to OUTPUT.
	name_blob = " ".join(
		filter(
			None,
			[
				(account.account_name or ""),
				(account.name or ""),
				(account.parent_account or ""),
			],
		)
	).lower()
	if any(word in name_blob for word in ("purchase", "input", "buy", "expense")):
		return DEFAULT_PURCHASE_REPORT_TAX_TYPE
	return DEFAULT_SALES_REPORT_TAX_TYPE


def _build_tax_rate_payload(account) -> dict:
	"""Build the Xero TaxRate payload from an ERPNext tax Account."""
	rate = flt(account.tax_rate)
	component_name = (account.account_name or account.name)[:50] or "Tax"

	return {
		"Name": (account.account_name or account.name)[:50],
		"ReportTaxType": _resolve_report_tax_type(account),
		"TaxComponents": [
			{
				"Name": component_name,
				"Rate": rate,
				"IsCompound": False,
				"IsNonRecoverable": False,
			}
		],
	}


def _validate_tax_account(account):
	if (account.account_type or "") != "Tax":
		frappe.throw(_("Account {0} is not a Tax account (account_type must be 'Tax')").format(account.name))
	if flt(account.tax_rate) <= 0:
		frappe.throw(
			_("Account {0} has no tax_rate. Set a non-zero tax_rate before syncing to Xero.").format(
				account.name
			)
		)


@frappe.whitelist()
def create_tax_rate(account_name: str, update: bool = False) -> dict:
	"""Push a single ERPNext Tax Account to Xero's /TaxRates endpoint.

	On success, the assigned Xero TaxType code is stored back on the Account as
	`custom_xero_tax_type`.
	"""
	account = frappe.get_doc("Account", account_name)
	_validate_tax_account(account)

	if account.get("custom_xero_tax_type") and not update:
		return {
			"status": "info",
			"message": _("Account already synced to Xero (TaxType {0}).").format(
				account.custom_xero_tax_type
			),
			"data": {"TaxType": account.custom_xero_tax_type},
		}

	payload = _build_tax_rate_payload(account)
	data = {"TaxRates": [payload]}

	client = get_xero_client()
	# Xero accepts both POST and PUT for TaxRates; POST creates new, and also
	# updates an existing TaxType when the payload includes one. PUT will fail
	# with "TaxType code is required" if the rate doesn't exist yet, so we use
	# POST in both create/update paths.
	if update and account.get("custom_xero_tax_type"):
		payload["TaxType"] = account.custom_xero_tax_type
		data = {"TaxRates": [payload]}

	response = client.make_request("POST", "/TaxRates", data=data)

	rates = (response or {}).get("TaxRates") or []
	if not rates:
		return {"status": "error", "message": "Failed to create TaxRate in Xero", "data": response}

	xero_tax = rates[0]
	tax_type = xero_tax.get("TaxType")
	if not tax_type:
		return {
			"status": "error",
			"message": _("Xero did not return a TaxType for {0}.").format(account.name),
			"data": xero_tax,
		}

	# Stamp Xero linkage back onto the ERPNext Account so subsequent invoice syncs
	# can resolve the TaxType from `Account.custom_xero_tax_type`.
	frappe.db.set_value("Account", account.name, "custom_xero_tax_type", tax_type)
	if xero_tax.get("ReportTaxType") and frappe.db.has_column("Account", "custom_xero_report_tax_type"):
		frappe.db.set_value(
			"Account",
			account.name,
			"custom_xero_report_tax_type",
			xero_tax.get("ReportTaxType"),
		)
	if not account.get("custom_send_to_xero"):
		frappe.db.set_value("Account", account.name, "custom_send_to_xero", 1)

	return {
		"status": "success",
		"message": _("Tax Rate synced to Xero. Saved Xero TaxType '{0}' on Account '{1}'.").format(
			tax_type, account.name
		),
		"data": xero_tax,
		"account": account.name,
		"tax_type": tax_type,
	}


@frappe.whitelist()
def sync_selected_tax_rates(accounts) -> dict:
	"""Bulk-sync a list of ERPNext Tax Accounts to Xero.

	Explicit user selection in the list view counts as intent to sync, so this
	does NOT require `custom_send_to_xero` to be checked. It still skips:
	- accounts that aren't Tax accounts
	- accounts already synced (have `custom_xero_tax_type`)
	"""
	names = frappe.parse_json(accounts) or []
	if not isinstance(names, list):
		frappe.throw(_("Invalid accounts payload"))

	results = {"created": [], "skipped": [], "failed": []}

	for name in names:
		if not name:
			continue
		try:
			account = frappe.get_doc("Account", name)
			if (account.account_type or "") != "Tax":
				results["skipped"].append({"name": name, "reason": "Not a Tax account"})
				continue
			if account.get("custom_xero_tax_type"):
				results["skipped"].append(
					{
						"name": name,
						"reason": f"Already synced (TaxType {account.custom_xero_tax_type})",
					}
				)
				continue

			res = create_tax_rate(name, update=False)
			if res and res.get("status") == "success":
				# Also flip the checkbox so the form reflects the synced state
				if not account.get("custom_send_to_xero"):
					frappe.db.set_value("Account", name, "custom_send_to_xero", 1)
				results["created"].append({"name": name, "tax_type": (res.get("data") or {}).get("TaxType")})
			else:
				results["failed"].append({"name": name, "error": (res or {}).get("message") or "Unknown"})
		except Exception as e:
			results["failed"].append({"name": name, "error": str(e)})

	return results


def _find_tax_parent_account(company: str) -> str | None:
	"""Best-effort lookup of a group account suitable as parent for new Tax accounts.

	Tries, in order:
	1. A group account already marked as Tax (`account_type="Tax"`, `is_group=1`)
	2. A group account literally named "Duties and Taxes" (the default in CoA)
	3. Any non-root group account under root_type="Liability"
	"""
	# 1. Existing Tax group
	parent = frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Tax", "is_group": 1, "disabled": 0},
		"name",
		order_by="lft asc",
	)
	if parent:
		return parent

	# 2. Default Duties and Taxes group from standard CoA
	parent = frappe.db.get_value(
		"Account",
		{"company": company, "account_name": "Duties and Taxes", "is_group": 1, "disabled": 0},
		"name",
		order_by="lft asc",
	)
	if parent:
		return parent

	# 3. Any non-root group account under Liability
	parent = frappe.db.get_value(
		"Account",
		[
			["company", "=", company],
			["is_group", "=", 1],
			["root_type", "=", "Liability"],
			["disabled", "=", 0],
			["parent_account", "is", "set"],
		],
		"name",
		order_by="lft asc",
	)
	return parent


def _xero_effective_rate(rate: dict) -> float:
	"""Resolve the effective tax rate for a Xero TaxRate payload.

	Xero returns the per-component rate under `TaxComponents[].Rate`. For simple
	(non-compound) rates we sum the non-compound components. As a fallback we use
	the top-level `EffectiveRate` field Xero reports for the whole TaxRate.
	"""
	components = rate.get("TaxComponents") or []
	component_total = float(sum(flt(c.get("Rate")) for c in components if not c.get("IsCompound")))
	if component_total:
		return component_total

	# Fallback: top-level EffectiveRate (or any component rate when all are compound)
	effective = rate.get("EffectiveRate")
	if effective is not None:
		return float(flt(effective))
	if components:
		return float(sum(flt(c.get("Rate")) for c in components))
	return 0.0


def _create_tax_account_from_xero(rate: dict, company: str, parent_account: str) -> str | None:
	"""Create an ERPNext Tax Account from a Xero TaxRate. Returns the new account name."""
	xero_name = (rate.get("Name") or "").strip()
	if not xero_name:
		return None

	# Avoid duplicates under the same parent / company
	existing = frappe.db.get_value(
		"Account",
		{"company": company, "account_name": xero_name},
		"name",
	)
	if existing:
		return existing

	effective_rate = _xero_effective_rate(rate)

	account = frappe.new_doc("Account")
	account.account_name = xero_name
	account.parent_account = parent_account
	account.company = company
	account.account_type = "Tax"
	account.is_group = 0
	account.tax_rate = effective_rate
	# Inherit root/report type from parent (Frappe will derive if left blank)
	account.flags.ignore_permissions = True
	account.insert()

	# Persist tax_rate explicitly: some Account controller flows can ignore the
	# in-memory value during the initial insert validate pass, so re-stamp it.
	if effective_rate:
		frappe.db.set_value("Account", account.name, "tax_rate", effective_rate)

	# Stamp Xero linkage so we don't re-create on the next pull
	updates = {
		"custom_xero_tax_type": rate.get("TaxType"),
		"custom_send_to_xero": 1,
	}
	if rate.get("ReportTaxType"):
		updates["custom_xero_report_tax_type"] = rate.get("ReportTaxType")
	for fieldname, value in updates.items():
		if frappe.db.has_column("Account", fieldname):
			frappe.db.set_value("Account", account.name, fieldname, value)

	return account.name


@frappe.whitelist()
def pull_tax_rates_from_xero(company: str | None = None, parent_account: str | None = None) -> dict:
	"""Pull all TaxRates from Xero into ERPNext.

	Behaviour per Xero TaxRate:
	- If a matching ERPNext Tax account exists (case-insensitive name match):
	  back-fill `custom_xero_tax_type` (and `custom_xero_report_tax_type`).
	- Otherwise: CREATE a new ERPNext Tax account under the supplied
	  Company / Parent Account (or auto-detected ones) and stamp the linkage.

	Args:
	    company: target Company for newly-created Tax accounts. Defaults to the
	             single Company on the site, or `frappe.defaults`'s default.
	    parent_account: group Account to nest new Tax accounts under. Auto-detected
	                    via `_find_tax_parent_account()` when not provided.
	"""
	# Resolve company
	if not company:
		companies = frappe.get_all("Company", pluck="name")
		if len(companies) == 1:
			company = companies[0]
		else:
			company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default(
				"company"
			)
	if not company:
		frappe.throw(_("Could not resolve a default Company. Pass `company` explicitly."))

	# Resolve parent account
	if not parent_account:
		parent_account = _find_tax_parent_account(company)
	if not parent_account:
		frappe.throw(
			_(
				"No suitable parent account found under Company {0}. "
				"Create a group account (e.g. 'Duties and Taxes') and pass it as `parent_account`."
			).format(company)
		)

	client = get_xero_client()
	response = client.make_request("GET", "/TaxRates") or {}
	rates = response.get("TaxRates") or []

	# Index existing Tax accounts under the target company so we don't try to
	# re-create them (and so we can back-fill the TaxType / tax_rate on a match).
	tax_accounts = frappe.get_all(
		"Account",
		filters={"account_type": "Tax", "company": company},
		fields=["name", "account_name", "custom_xero_tax_type", "tax_rate"],
	)
	by_name = {(a.account_name or "").strip().lower(): a for a in tax_accounts}

	mapped: list[dict] = []
	created: list[dict] = []
	skipped: list[dict] = []
	failed: list[dict] = []

	for r in rates:
		tax_type = r.get("TaxType")
		xero_name_raw = (r.get("Name") or "").strip()
		xero_name = xero_name_raw.lower()
		if not tax_type or not xero_name_raw:
			skipped.append({"xero_name": xero_name_raw, "reason": "Missing TaxType or Name in Xero payload"})
			continue

		match = by_name.get(xero_name)
		if match:
			effective_rate = _xero_effective_rate(r)
			rate_needs_update = effective_rate and flt(match.tax_rate) != flt(effective_rate)
			already_linked = match.custom_xero_tax_type == tax_type

			if already_linked and not rate_needs_update:
				skipped.append(
					{"xero_name": xero_name_raw, "reason": "Already mapped", "account": match.name}
				)
				continue

			if not already_linked:
				frappe.db.set_value("Account", match.name, "custom_xero_tax_type", tax_type)
			if r.get("ReportTaxType") and frappe.db.has_column("Account", "custom_xero_report_tax_type"):
				frappe.db.set_value(
					"Account", match.name, "custom_xero_report_tax_type", r.get("ReportTaxType")
				)
			if rate_needs_update:
				frappe.db.set_value("Account", match.name, "tax_rate", effective_rate)
			mapped.append({"account": match.name, "tax_type": tax_type, "tax_rate": effective_rate})
			continue

		# No match -> create
		try:
			new_name = _create_tax_account_from_xero(r, company=company, parent_account=parent_account)
			if new_name:
				created.append({"account": new_name, "tax_type": tax_type, "xero_name": xero_name_raw})
		except Exception as e:
			failed.append({"xero_name": xero_name_raw, "error": str(e)})

	return {
		"company": company,
		"parent_account": parent_account,
		"mapped": mapped,
		"created": created,
		"skipped": skipped,
		"failed": failed,
	}
