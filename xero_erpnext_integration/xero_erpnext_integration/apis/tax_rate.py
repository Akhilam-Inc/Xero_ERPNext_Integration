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

# Xero requires ReportTaxType when creating rates for these countries only.
# US / Global orgs must omit it (even if some existing rates carry legacy values).
_REPORT_TAX_TYPE_COUNTRIES = frozenset({"AU", "NZ", "GB", "UK", "SG"})

# Report tax types that exist on some orgs but must not be used when creating rates.
_NON_CREATABLE_REPORT_TAX_TYPES = frozenset(
	{
		"AVALARA",
		"GSTONIMPORTS",
		"BASEXCLUDED",
		"MOSSSALES",
		"MOSSSALESOUTOFEU",
		"MOSSPURCHASES",
		"MOSSPURCHASESOUTOFEU",
	}
)


def _xero_bool(value) -> bool:
	if value is True:
		return True
	if value is False or value is None:
		return False
	return str(value).strip().lower() in ("true", "1", "yes")


def _account_is_purchase_side(account) -> bool:
	"""Heuristic: purchase/input tax accounts vs sales/output."""
	name_blob = " ".join(
		part
		for part in [
			(account.account_name or ""),
			(account.name or ""),
			(account.parent_account or ""),
		]
		if part
	).lower()
	return any(word in name_blob for word in ("purchase", "input", "buy", "expense"))


def _get_org_country_code(client) -> str | None:
	cache = getattr(frappe.local, "_xero_org_country_code", None)
	if cache is not None:
		return cache or None

	code = None
	try:
		response = client.make_request("GET", "/Organisation") or {}
		orgs = response.get("Organisations") or []
		if orgs:
			code = (orgs[0].get("CountryCode") or "").strip().upper() or None
	except Exception:
		pass

	frappe.local._xero_org_country_code = code or ""
	return code


def _get_xero_tax_rates(client, *, refresh: bool = False) -> list[dict]:
	if not refresh and hasattr(frappe.local, "_xero_tax_rates_cache"):
		return frappe.local._xero_tax_rates_cache

	response = client.make_request("GET", "/TaxRates") or {}
	rates = response.get("TaxRates") or []
	frappe.local._xero_tax_rates_cache = rates
	return rates


def _org_requires_report_tax_type(client, xero_rates: list[dict] | None = None) -> bool:
	"""True only for regional orgs where Xero mandates ReportTaxType on POST."""
	del xero_rates  # country alone determines requirement
	country = _get_org_country_code(client)
	return country in _REPORT_TAX_TYPE_COUNTRIES


def _valid_report_tax_types(xero_rates: list[dict]) -> set[str]:
	return {
		(r.get("ReportTaxType") or "").strip() for r in xero_rates if (r.get("ReportTaxType") or "").strip()
	}


def _report_tax_type_allowed_for_create(report_type: str, target_rate: float) -> bool:
	if not report_type:
		return False
	if report_type in _NON_CREATABLE_REPORT_TAX_TYPES:
		return False
	return not (report_type == "NONE" and target_rate)


def _preferred_report_tax_type_prefix(purchase: bool) -> str:
	return "INPUT" if purchase else "OUTPUT"


def _pick_report_tax_type_from_rates(account, xero_rates: list[dict]) -> str | None:
	"""Choose a ReportTaxType from existing Xero rates safe for creating new rates."""
	purchase = _account_is_purchase_side(account)
	target_rate = flt(account.tax_rate)
	prefix = _preferred_report_tax_type_prefix(purchase)
	candidates: list[tuple[tuple, str]] = []

	for rate in xero_rates:
		if (rate.get("Status") or "ACTIVE").upper() != "ACTIVE":
			continue
		report_type = (rate.get("ReportTaxType") or "").strip()
		if not _report_tax_type_allowed_for_create(report_type, target_rate):
			continue

		can_revenue = _xero_bool(rate.get("CanApplyToRevenue"))
		can_expenses = _xero_bool(rate.get("CanApplyToExpenses"))
		if purchase:
			if not can_expenses:
				continue
			strictness = 0 if not can_revenue else 1
		else:
			if not can_revenue:
				continue
			strictness = 0 if not can_expenses else 1

		effective = _xero_effective_rate(rate)
		rate_delta = abs(effective - target_rate) if target_rate else 999
		prefix_match = 0 if report_type.startswith(prefix) else 1
		modern_bonus = 0 if report_type.endswith("2") else 1
		sort_key = (prefix_match, rate_delta, strictness, modern_bonus, report_type)
		candidates.append((sort_key, report_type))

	if not candidates:
		return None

	candidates.sort(key=lambda item: item[0])
	return candidates[0][1]

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

	valid_names = [n for n in names if n]
	results = {"created": [], "skipped": [], "failed": []}

	if not valid_names:
		return results

	# Batch-fetch all screening fields in one query — avoids N+1 (AKH-02)
	account_rows = frappe.get_all(
		"Account",
		filters=[["name", "in", valid_names]],
		fields=["name", "account_type", "custom_xero_tax_type", "custom_send_to_xero"],
	)
	account_map = {row.name: row for row in account_rows}

	for name in valid_names:
		try:
			account = account_map.get(name)
			if not account:
				results["failed"].append({"name": name, "error": "Account not found"})
				continue

			if (account.account_type or "") != "Tax":
				results["skipped"].append({"name": name, "reason": "Not a Tax account"})
				continue
			if account.custom_xero_tax_type:
				results["skipped"].append(
					{"name": name, "reason": f"Already synced (TaxType {account.custom_xero_tax_type})"}
				)
				continue

			# create_tax_rate loads the full doc internally (needs tax_rate, account_name, etc.)
			res = create_tax_rate(name, update=False)
			if res and res.get("status") == "success":
				if not account.custom_send_to_xero:
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
	components = rate.get("TaxComponents") or []
	return float(sum(flt(c.get("Rate")) for c in components if not c.get("IsCompound")))


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

	account = frappe.new_doc("Account")
	account.account_name = xero_name
	account.parent_account = parent_account
	account.company = company
	account.account_type = "Tax"
	account.is_group = 0
	account.tax_rate = _xero_effective_rate(rate)
	# Inherit root/report type from parent (Frappe will derive if left blank)
	account.flags.ignore_permissions = True
	account.insert()

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
	# re-create them (and so we can back-fill the TaxType on a match).
	tax_accounts = frappe.get_all(
		"Account",
		filters={"account_type": "Tax", "company": company},
		fields=["name", "account_name", "custom_xero_tax_type"],
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
			if match.custom_xero_tax_type == tax_type:
				skipped.append(
					{"xero_name": xero_name_raw, "reason": "Already mapped", "account": match.name}
				)
				continue
			frappe.db.set_value("Account", match.name, "custom_xero_tax_type", tax_type)
			if r.get("ReportTaxType") and frappe.db.has_column("Account", "custom_xero_report_tax_type"):
				frappe.db.set_value(
					"Account", match.name, "custom_xero_report_tax_type", r.get("ReportTaxType")
				)
			mapped.append({"account": match.name, "tax_type": tax_type})
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
