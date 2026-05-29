# Copyright (c) 2025, nasirucode and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate import (
	_build_tax_rate_payload,
	_pick_report_tax_type_from_rates,
	_resolve_report_tax_type,
	_resolve_response_report_tax_type,
)

US_RATES = [
	{
		"Name": "Auto Look Up",
		"TaxType": "AVALARA",
		"ReportTaxType": "AVALARA",
		"CanApplyToRevenue": "true",
		"CanApplyToExpenses": "true",
		"EffectiveRate": "0.0000",
		"Status": "ACTIVE",
		"TaxComponents": [{"Rate": "0.0000", "IsCompound": False}],
	},
	{
		"Name": "Tax on Sales",
		"TaxType": "OUTPUT",
		"ReportTaxType": "OUTPUT",
		"CanApplyToRevenue": "true",
		"CanApplyToExpenses": "true",
		"EffectiveRate": "0.0000",
		"Status": "ACTIVE",
		"TaxComponents": [{"Rate": "0.0000", "IsCompound": False}],
	},
	{
		"Name": "Tax on Purchases",
		"TaxType": "INPUT",
		"ReportTaxType": "INPUT",
		"CanApplyToRevenue": "true",
		"CanApplyToExpenses": "true",
		"EffectiveRate": "0.0000",
		"Status": "ACTIVE",
		"TaxComponents": [{"Rate": "0.0000", "IsCompound": False}],
	},
]

NZ_RATES = [
	{
		"Name": "15% GST on Expenses",
		"TaxType": "INPUT2",
		"ReportTaxType": "INPUT2",
		"CanApplyToRevenue": "false",
		"CanApplyToExpenses": "true",
		"EffectiveRate": "15.0000",
		"Status": "ACTIVE",
		"TaxComponents": [{"Rate": "15.0000", "IsCompound": False}],
	},
	{
		"Name": "15% GST on Income",
		"TaxType": "OUTPUT2",
		"ReportTaxType": "OUTPUT2",
		"CanApplyToRevenue": "true",
		"CanApplyToExpenses": "false",
		"EffectiveRate": "15.0000",
		"Status": "ACTIVE",
		"TaxComponents": [{"Rate": "15.0000", "IsCompound": False}],
	},
	{
		"Name": "No GST",
		"TaxType": "NONE",
		"ReportTaxType": "NONE",
		"CanApplyToRevenue": "true",
		"CanApplyToExpenses": "true",
		"EffectiveRate": "0.0000",
		"Status": "ACTIVE",
		"TaxComponents": [{"Rate": "0.0000", "IsCompound": False}],
	},
]


class TestReportTaxTypeResolution(FrappeTestCase):
	def test_nz_sales_account_prefers_output2(self):
		account = frappe._dict(
			account_name="GST 15%",
			name="GST 15% - TC",
			parent_account="Duties and Taxes - TC",
			tax_rate=15,
		)
		self.assertEqual(_pick_report_tax_type_from_rates(account, NZ_RATES), "OUTPUT2")

	def test_nz_purchase_account_prefers_input2(self):
		account = frappe._dict(
			account_name="Purchase GST 15%",
			name="Purchase GST 15% - TC",
			parent_account="Duties and Taxes - TC",
			tax_rate=15,
		)
		self.assertEqual(_pick_report_tax_type_from_rates(account, NZ_RATES), "INPUT2")

	@patch(
		"xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate._get_xero_tax_rates",
		return_value=NZ_RATES,
	)
	@patch(
		"xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate._get_org_country_code",
		return_value="NZ",
	)
	@patch(
		"xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate._org_requires_report_tax_type",
		return_value=True,
	)
	def test_build_payload_uses_output2_not_output(self, *_mocks):
		account = frappe._dict(
			account_name="GST 15%",
			name="GST 15% - TC",
			parent_account="Duties and Taxes - TC",
			tax_rate=15,
		)
		payload = _build_tax_rate_payload(account, client=MagicMock())
		self.assertEqual(payload.get("ReportTaxType"), "OUTPUT2")
		self.assertNotEqual(payload.get("ReportTaxType"), "OUTPUT")

	@patch(
		"xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate._get_xero_tax_rates",
		return_value=US_RATES,
	)
	@patch(
		"xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate._get_org_country_code",
		return_value="US",
	)
	def test_us_payload_omits_report_tax_type(self, *_mocks):
		account = frappe._dict(
			account_name="Sales Tax",
			name="Sales Tax - TC",
			tax_rate=8.25,
		)
		payload = _build_tax_rate_payload(account, client=MagicMock())
		self.assertNotIn("ReportTaxType", payload)

	@patch(
		"xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate._get_xero_tax_rates",
		return_value=US_RATES,
	)
	def test_us_picker_ignores_avalara(self, *_mocks):
		account = frappe._dict(
			account_name="Test Tax @5%",
			name="Test Tax @5% - TC",
			tax_rate=5,
		)
		self.assertEqual(_pick_report_tax_type_from_rates(account, US_RATES), "OUTPUT")

	def test_response_resolver_uses_response_value(self):
		client = MagicMock()
		result = _resolve_response_report_tax_type(
			xero_tax={"ReportTaxType": "OUTPUT2"},
			payload={"ReportTaxType": "OUTPUT"},
			client=client,
			tax_type="OUTPUT2",
		)
		self.assertEqual(result, "OUTPUT2")
		client.make_request.assert_not_called()

	def test_response_resolver_falls_back_to_get(self):
		client = MagicMock()
		client.make_request.return_value = {"TaxRates": [{"ReportTaxType": "INPUT2"}]}
		result = _resolve_response_report_tax_type(
			xero_tax={"TaxType": "TAX007"},
			payload={},
			client=client,
			tax_type="TAX007",
		)
		self.assertEqual(result, "INPUT2")
		client.make_request.assert_called_once_with("GET", "/TaxRates/TAX007")

	def test_response_resolver_falls_back_to_payload(self):
		client = MagicMock()
		client.make_request.return_value = {"TaxRates": [{}]}
		result = _resolve_response_report_tax_type(
			xero_tax={},
			payload={"ReportTaxType": "OUTPUT"},
			client=client,
			tax_type="TAX007",
		)
		self.assertEqual(result, "OUTPUT")

	def test_response_resolver_returns_none_when_unknown(self):
		client = MagicMock()
		client.make_request.return_value = {"TaxRates": [{}]}
		result = _resolve_response_report_tax_type(
			xero_tax={}, payload={}, client=client, tax_type="TAX007"
		)
		self.assertIsNone(result)

	def test_response_resolver_local_label_for_sales_account(self):
		client = MagicMock()
		client.make_request.return_value = {"TaxRates": [{}]}
		account = frappe._dict(
			account_name="Sales Tax 5%",
			name="Sales Tax 5% - TC",
			parent_account="Duties and Taxes - TC",
		)
		result = _resolve_response_report_tax_type(
			xero_tax={}, payload={}, client=client, tax_type="TAX007", account=account
		)
		self.assertEqual(result, "OUTPUT")

	def test_response_resolver_local_label_for_purchase_account(self):
		client = MagicMock()
		client.make_request.return_value = {"TaxRates": [{}]}
		account = frappe._dict(
			account_name="Purchase Tax 5%",
			name="Purchase Tax 5% - TC",
			parent_account="Duties and Taxes - TC",
		)
		result = _resolve_response_report_tax_type(
			xero_tax={}, payload={}, client=client, tax_type="TAX007", account=account
		)
		self.assertEqual(result, "INPUT")

	@patch(
		"xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate._get_xero_tax_rates",
		return_value=NZ_RATES,
	)
	@patch(
		"xero_erpnext_integration.xero_erpnext_integration.apis.tax_rate._org_requires_report_tax_type",
		return_value=True,
	)
	def test_explicit_invalid_report_tax_type_throws(self, *_mocks):
		account = frappe._dict(
			account_name="GST 15%",
			name="GST 15% - TC",
			tax_rate=15,
			custom_xero_report_tax_type="OUTPUT",
		)
		with self.assertRaises(frappe.ValidationError):
			_resolve_report_tax_type(account, client=MagicMock())
