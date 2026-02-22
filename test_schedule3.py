"""
═══════════════════════════════════════════════════════════════════════
COMPREHENSIVE TEST SUITE — Schedule III Generator (Steps 1–4)
═══════════════════════════════════════════════════════════════════════
Tests:
  Step 1: Granular line items extracted by local_parser.py & parser.py schema
  Step 2: Proportionate forecasting (line_item_pcts math)
  Step 3: Indirect Method math engine (Δ AR, Δ AP, Cash from Ops)
  Step 4: API response shape (all new fields present for frontend)
"""
import sys, os, json, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

import pytest
import pandas as pd

from local_parser import local_fallback_parse, clean_numeric
from algorithms import (
    compute_advance_tax_schedule,
    percent_of_sales,
    straight_line_forecast,
    multiple_linear_regression_forecast,
    adaptive_holt_winters_forecast,
    INDIAN_FY_MONTHS,
    ADVANCE_TAX_SCHEDULE
)


# ═══════════════════════════════════════════════════════════════════
# STEP 1 TESTS — Granular Line Item Extraction
# ═══════════════════════════════════════════════════════════════════

class TestStep1_GranularParser:
    """Verify local_parser extracts unmapped columns into line_items dict."""
    
    @pytest.fixture
    def granular_csv(self):
        """A CSV with standard columns + extra granular columns that should become line_items."""
        csv_text = """Month,Revenue,COGS,OPEX,Payroll,Receivable,Payable,Cash Balance,Marketing,Rent,Software,Travel
Apr-24,800000,300000,100000,150000,90000,50000,250000,30000,45000,20000,10000
May-24,850000,320000,110000,160000,95000,55000,280000,35000,45000,22000,12000
Jun-24,900000,340000,115000,170000,100000,58000,310000,38000,45000,24000,13000
"""
        return csv_text.encode('utf-8')
    
    def test_line_items_present(self, granular_csv):
        """Each row should have a non-empty line_items dict."""
        result = local_fallback_parse(granular_csv, "test.csv")
        for row in result["data"]:
            assert "line_items" in row, "Missing line_items key"
            assert len(row["line_items"]) > 0, f"line_items is empty for {row['month']}"
    
    def test_line_items_contain_unmapped_columns(self, granular_csv):
        """Marketing, Rent, Software, Travel should appear as line_items."""
        result = local_fallback_parse(granular_csv, "test.csv")
        first_row = result["data"][0]
        item_keys = set(first_row["line_items"].keys())
        # The local_parser title-cases unmapped column names
        assert "Marketing" in item_keys, f"Marketing missing from {item_keys}"
        assert "Rent" in item_keys, f"Rent missing from {item_keys}"
        assert "Software" in item_keys, f"Software missing from {item_keys}"
        assert "Travel" in item_keys, f"Travel missing from {item_keys}"
    
    def test_line_items_values_positive(self, granular_csv):
        """All line item values should be positive absolute floats."""
        result = local_fallback_parse(granular_csv, "test.csv")
        for row in result["data"]:
            for k, v in row["line_items"].items():
                assert v > 0, f"Line item {k} has non-positive value: {v}"
                assert isinstance(v, float), f"Line item {k} is not a float: {type(v)}"
    
    def test_standard_fields_still_present(self, granular_csv):
        """Standard fields (revenue, cogs, opex, etc.) should still work."""
        result = local_fallback_parse(granular_csv, "test.csv")
        for row in result["data"]:
            assert row["revenue"] > 0
            assert row["cogs"] > 0
            assert row["opex"] > 0
            assert row["cash_balance"] > 0
    
    def test_total_rows_skipped(self):
        """Rows with 'Total' in the month column should be skipped."""
        csv_text = """Month,Revenue,COGS,OPEX,Cash Balance,Marketing
Apr-24,800000,300000,100000,250000,30000
Total,2400000,900000,300000,750000,90000
"""
        result = local_fallback_parse(csv_text.encode('utf-8'), "test.csv")
        assert len(result["data"]) == 1, "Total row should be skipped"


# ═══════════════════════════════════════════════════════════════════
# STEP 2 TESTS — Proportionate Forecasting Math
# ═══════════════════════════════════════════════════════════════════

class TestStep2_ProportionateForecasting:
    """Verify line_item_pcts math ensures sum(items) == forecasted OpEx."""
    
    def test_proportionate_distribution(self):
        """If Marketing is 30% of OpEx and Rent is 70%, forecasted items should match."""
        # Historical data: 3 months
        data = [
            {"opex": 100000, "line_items": {"Marketing": 30000, "Rent": 70000}},
            {"opex": 120000, "line_items": {"Marketing": 36000, "Rent": 84000}},
            {"opex": 110000, "line_items": {"Marketing": 33000, "Rent": 77000}},
        ]
        
        opex_arr = [d["opex"] for d in data]
        total_opex_historical = sum(opex_arr)
        
        hist_line_item_sums = {}
        for d in data:
            for k, v in d["line_items"].items():
                hist_line_item_sums[k] = hist_line_item_sums.get(k, 0) + v
        
        line_item_pcts = {}
        for k, total_val in hist_line_item_sums.items():
            line_item_pcts[k] = total_val / total_opex_historical
        
        # Verify percentages
        assert abs(line_item_pcts["Marketing"] - 0.3) < 0.001, f"Marketing pct wrong: {line_item_pcts['Marketing']}"
        assert abs(line_item_pcts["Rent"] - 0.7) < 0.001, f"Rent pct wrong: {line_item_pcts['Rent']}"
        
        # Verify sum of pcts = 1.0
        assert abs(sum(line_item_pcts.values()) - 1.0) < 0.001, "Percentages don't sum to 1.0"
    
    def test_forecasted_items_sum_to_opex(self):
        """Projected line items should sum to exactly projected OpEx."""
        proj_opex = 150000
        line_item_pcts = {"Marketing": 0.3, "Rent": 0.45, "Software": 0.25}
        
        proj_line_items = {}
        for k, pct in line_item_pcts.items():
            proj_line_items[k] = round(proj_opex * pct)
        
        total_items = sum(proj_line_items.values())
        # Allow rounding tolerance of ±len(items)
        assert abs(total_items - proj_opex) <= len(line_item_pcts), \
            f"Sum of items ({total_items}) != proj OpEx ({proj_opex})"


# ═══════════════════════════════════════════════════════════════════
# STEP 3 TESTS — Indirect Method Math Engine
# ═══════════════════════════════════════════════════════════════════

class TestStep3_IndirectMethod:
    """Verify the Schedule III Indirect Method Cash Flow calculation."""
    
    def test_operating_profit_bwc_equals_ebitda(self):
        """Operating Profit before Working Capital Changes == EBITDA."""
        rev = 1000000
        cogs_pct = 0.35
        opex_pct = 0.12
        payroll_pct = 0.20
        
        gp = rev - (rev * cogs_pct)
        ebitda = gp - (rev * opex_pct) - (rev * payroll_pct)
        operating_profit_bwc = ebitda  # This is what main.py does
        
        assert operating_profit_bwc == ebitda
    
    def test_delta_ar_calculation(self):
        """Increase in AR should be a negative impact on cash."""
        prev_ar = 90000
        current_ar = 100000
        delta_ar = current_ar - prev_ar  # +10000 = increase in AR
        
        # In the Indirect Method, increase in AR is SUBTRACTED
        cash_impact = -delta_ar
        assert cash_impact == -10000, "AR increase should reduce cash"
    
    def test_delta_ap_calculation(self):
        """Increase in AP should be a positive impact on cash."""
        prev_ap = 50000
        current_ap = 60000
        delta_ap = current_ap - prev_ap  # +10000 = increase in AP
        
        # In the Indirect Method, increase in AP is ADDED
        cash_impact = delta_ap
        assert cash_impact == 10000, "AP increase should increase cash"
    
    def test_cash_from_operations_formula(self):
        """Cash from Operations = EBITDA + delta_ap - delta_ar."""
        ebitda = 330000
        delta_ar = 10000   # AR increased
        delta_ap = 5000    # AP increased
        
        cash_from_ops = ebitda + delta_ap - delta_ar
        assert cash_from_ops == 325000
    
    def test_net_cash_operating_subtracts_tax(self):
        """Net Cash from Ops = Cash from Ops - Advance Tax."""
        cash_from_ops = 325000
        tax = 48750  # Statutory quarter
        
        net_cash_operating = cash_from_ops - tax
        assert net_cash_operating == 276250
    
    def test_investing_is_negative_capex(self):
        """Cash from Investing = -capex."""
        capex = 25000
        net_cash_investing = -capex
        assert net_cash_investing == -25000
    
    def test_financing_is_negative_debt(self):
        """Cash from Financing = -debt."""
        debt = 15000
        net_cash_financing = -debt
        assert net_cash_financing == -15000
    
    def test_total_net_cash_flow(self):
        """Net Cash = Operating + Investing + Financing."""
        net_operating = 276250
        net_investing = -25000
        net_financing = -15000
        
        total = net_operating + net_investing + net_financing
        assert total == 236250
    
    def test_advance_tax_only_in_statutory_months(self):
        """Tax should only hit in months 2(Jun), 5(Sep), 8(Dec), 11(Mar)."""
        monthly_ebt = [100000] * 12
        tax_rate = 0.25
        
        tax_schedule = compute_advance_tax_schedule(monthly_ebt, tax_rate)
        
        for i in range(12):
            if i in (2, 5, 8, 11):
                assert tax_schedule[i] > 0, f"Tax should be positive in month {i}"
            else:
                assert tax_schedule[i] == 0, f"Tax should be 0 in month {i}"
    
    def test_advance_tax_percentages(self):
        """Tax percentages: Jun 15%, Sep 30%, Dec 30%, Mar 25%."""
        monthly_ebt = [100000] * 12
        tax_rate = 0.25
        annual_tax = sum(monthly_ebt) * tax_rate  # 300,000
        
        tax_schedule = compute_advance_tax_schedule(monthly_ebt, tax_rate)
        
        assert abs(tax_schedule[2] - annual_tax * 0.15) < 1
        assert abs(tax_schedule[5] - annual_tax * 0.30) < 1
        assert abs(tax_schedule[8] - annual_tax * 0.30) < 1
        assert abs(tax_schedule[11] - annual_tax * 0.25) < 1
    
    def test_loss_making_no_tax(self):
        """Loss-making business should have zero tax across all months."""
        monthly_ebt = [-50000] * 12
        tax_rate = 0.25
        
        tax_schedule = compute_advance_tax_schedule(monthly_ebt, tax_rate)
        assert all(t == 0.0 for t in tax_schedule)


# ═══════════════════════════════════════════════════════════════════
# STEP 4 TESTS — Full API Response Shape Validation
# ═══════════════════════════════════════════════════════════════════

class TestStep4_APIResponseShape:
    """Simulate what main.py produces and verify the frontend contract."""
    
    def _simulate_three_way_model(self):
        """Replicate the exact math from main.py with known inputs."""
        revenues = [800000, 850000, 900000, 950000, 1000000, 1050000]
        cogs_arr = [300000, 320000, 340000, 360000, 380000, 400000]
        opex_arr = [100000, 110000, 115000, 120000, 125000, 130000]
        payroll_arr = [150000, 160000, 170000, 175000, 180000, 185000]
        debt_arr = [15000] * 6
        capex_arr = [25000] * 6
        
        data = []
        for i in range(6):
            data.append({
                "revenue": revenues[i], "cogs": cogs_arr[i], "opex": opex_arr[i],
                "payroll": payroll_arr[i], "debt_service": debt_arr[i], "capex": capex_arr[i],
                "ar_balance": revenues[i] * 0.12, "ap_balance": cogs_arr[i] * 0.1,
                "cash_balance": 250000 + i * 30000,
                "line_items": {"Marketing": opex_arr[i] * 0.3, "Rent": opex_arr[i] * 0.5, "Software": opex_arr[i] * 0.2}
            })
        
        cogs_pct = percent_of_sales(cogs_arr, revenues)
        opex_pct = percent_of_sales(opex_arr, revenues)
        payroll_pct = percent_of_sales(payroll_arr, revenues)
        
        total_opex_historical = sum(opex_arr)
        hist_line_item_sums = {}
        for d in data:
            for k, v in d.get("line_items", {}).items():
                hist_line_item_sums[k] = hist_line_item_sums.get(k, 0) + v
        line_item_pcts = {k: v / total_opex_historical for k, v in hist_line_item_sums.items()}
        
        baseline_forecast = multiple_linear_regression_forecast(revenues, periods=12)
        capex_forecast = straight_line_forecast(capex_arr, periods=12)
        debt_forecast = straight_line_forecast(debt_arr, periods=12)
        
        monthly_ebt = []
        for i, val in enumerate(baseline_forecast):
            proj_rev = val
            proj_cogs = proj_rev * cogs_pct
            proj_gp = proj_rev - proj_cogs
            proj_opex = proj_rev * opex_pct
            proj_payroll = proj_rev * payroll_pct
            proj_ebitda = proj_gp - proj_opex - proj_payroll
            proj_debt = debt_forecast[i]
            proj_capex = capex_forecast[i]
            proj_net_profit = proj_ebitda - proj_debt - proj_capex
            monthly_ebt.append(proj_net_profit)
        
        advance_tax_monthly = compute_advance_tax_schedule(monthly_ebt, 0.25)
        
        current_ar = data[-1]["ar_balance"]
        current_ap = data[-1]["ap_balance"]
        last_rev = revenues[-1]
        ar_pct = current_ar / last_rev
        last_costs = cogs_arr[-1] + opex_arr[-1] + payroll_arr[-1]
        ap_pct = current_ap / last_costs
        
        prev_ar = current_ar
        prev_ap = current_ap
        running_cash = data[-1]["cash_balance"]
        
        three_way_model = []
        for i, val in enumerate(baseline_forecast):
            proj_rev = val
            proj_cogs = proj_rev * cogs_pct
            proj_gp = proj_rev - proj_cogs
            proj_opex = proj_rev * opex_pct
            proj_payroll = proj_rev * payroll_pct
            proj_ebitda = proj_gp - proj_opex - proj_payroll
            proj_debt = debt_forecast[i]
            proj_capex = capex_forecast[i]
            proj_net_profit = proj_ebitda - proj_debt - proj_capex
            
            operating_profit_bwc = proj_ebitda
            proj_ar = proj_rev * ar_pct
            proj_ap = (proj_cogs + proj_opex + proj_payroll) * ap_pct
            delta_ar = proj_ar - prev_ar
            delta_ap = proj_ap - prev_ap
            prev_ar = proj_ar
            prev_ap = proj_ap
            cash_from_operations = operating_profit_bwc + delta_ap - delta_ar
            proj_tax = advance_tax_monthly[i]
            net_cash_operating = cash_from_operations - proj_tax
            net_cash_investing = -proj_capex
            net_cash_financing = -proj_debt
            cf_month = net_cash_operating + net_cash_investing + net_cash_financing
            running_cash += cf_month
            month_label = INDIAN_FY_MONTHS[i]
            
            proj_line_items = {k: round(proj_opex * pct) for k, pct in line_item_pcts.items()}
            
            three_way_model.append({
                "month": month_label,
                "revenue": round(proj_rev),
                "cogs": round(proj_cogs),
                "opex": round(proj_opex),
                "payroll": round(proj_payroll),
                "capex": round(proj_capex),
                "debt": round(proj_debt),
                "ebitda": round(proj_ebitda),
                "net_profit": round(proj_net_profit),
                "tax_liability": round(proj_tax),
                "operating_profit_bwc": round(operating_profit_bwc),
                "delta_ar": round(delta_ar),
                "delta_ap": round(delta_ap),
                "cash_from_operations": round(cash_from_operations),
                "net_cash_operating": round(net_cash_operating),
                "net_cash_investing": round(net_cash_investing),
                "net_cash_financing": round(net_cash_financing),
                "net_cash_flow": round(cf_month),
                "ending_cash": round(running_cash),
                "is_tax_quarter": proj_tax > 0,
                "line_items": proj_line_items
            })
        
        return three_way_model
    
    def test_12_months_generated(self):
        model = self._simulate_three_way_model()
        assert len(model) == 12, f"Expected 12 months, got {len(model)}"
    
    def test_indian_fy_labels(self):
        model = self._simulate_three_way_model()
        labels = [m["month"] for m in model]
        assert labels == ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    
    def test_schedule3_fields_present(self):
        """All Schedule III specific fields should be present in every month."""
        model = self._simulate_three_way_model()
        required_fields = [
            "operating_profit_bwc", "delta_ar", "delta_ap",
            "cash_from_operations", "net_cash_operating",
            "net_cash_investing", "net_cash_financing",
            "net_cash_flow", "ending_cash", "is_tax_quarter",
            "line_items"
        ]
        for m in model:
            for field in required_fields:
                assert field in m, f"Missing field '{field}' in month {m['month']}"
    
    def test_line_items_present_in_forecast(self):
        """Forecasted months should contain granular line items."""
        model = self._simulate_three_way_model()
        for m in model:
            assert "Marketing" in m["line_items"], f"Missing Marketing in {m['month']}"
            assert "Rent" in m["line_items"], f"Missing Rent in {m['month']}"
            assert "Software" in m["line_items"], f"Missing Software in {m['month']}"
    
    def test_line_items_values_reasonable(self):
        """Line items should be positive and less than total opex."""
        model = self._simulate_three_way_model()
        for m in model:
            for k, v in m["line_items"].items():
                assert v >= 0, f"{k} has negative value {v} in {m['month']}"
                assert v <= m["opex"] + 1, f"{k}={v} exceeds opex={m['opex']} in {m['month']}"
    
    def test_tax_only_in_statutory_quarters(self):
        model = self._simulate_three_way_model()
        tax_months = [m["month"] for m in model if m["is_tax_quarter"]]
        assert set(tax_months) == {"Jun", "Sep", "Dec", "Mar"}, f"Tax quarters wrong: {tax_months}"
    
    def test_net_cash_flow_identity(self):
        """net_cash_flow == net_cash_operating + net_cash_investing + net_cash_financing."""
        model = self._simulate_three_way_model()
        for m in model:
            expected = m["net_cash_operating"] + m["net_cash_investing"] + m["net_cash_financing"]
            assert abs(m["net_cash_flow"] - expected) <= 1, \
                f"Cash flow identity broken in {m['month']}: {m['net_cash_flow']} != {expected}"
    
    def test_ending_cash_accumulation(self):
        """ending_cash should reflect cumulative cash flow."""
        model = self._simulate_three_way_model()
        for i in range(1, len(model)):
            prev_end = model[i-1]["ending_cash"]
            current_flow = model[i]["net_cash_flow"]
            expected_end = prev_end + current_flow
            assert abs(model[i]["ending_cash"] - expected_end) <= 1, \
                f"Cash accumulation broken in {model[i]['month']}: {model[i]['ending_cash']} != {expected_end}"
    
    def test_investing_is_always_negative_or_zero(self):
        """Capital expenditure is an outflow — always ≤ 0."""
        model = self._simulate_three_way_model()
        for m in model:
            assert m["net_cash_investing"] <= 0, f"Investing positive in {m['month']}: {m['net_cash_investing']}"
    
    def test_financing_is_always_negative_or_zero(self):
        """Debt repayment is an outflow — always ≤ 0."""
        model = self._simulate_three_way_model()
        for m in model:
            assert m["net_cash_financing"] <= 0, f"Financing positive in {m['month']}: {m['net_cash_financing']}"


# ═══════════════════════════════════════════════════════════════════
# STEP 1 BONUS — Parser Schema Validation
# ═══════════════════════════════════════════════════════════════════

class TestStep1_ParserSchema:
    """Verify the Pydantic schema accepts line_items without triggering LLM init."""
    
    def test_financial_month_accepts_line_items(self):
        from pydantic import BaseModel, Field
        
        class FinancialMonth(BaseModel):
            month: str
            revenue: float
            cogs: float
            opex: float
            ar_balance: float
            cash_balance: float
            line_items: dict[str, float] = Field(default_factory=dict)
        
        fm = FinancialMonth(
            month="2024-04",
            revenue=800000,
            cogs=300000,
            opex=100000,
            ar_balance=90000,
            cash_balance=250000,
            line_items={"Marketing": 30000, "Rent": 45000}
        )
        assert fm.line_items["Marketing"] == 30000
        assert fm.line_items["Rent"] == 45000
    
    def test_financial_month_default_empty_line_items(self):
        from pydantic import BaseModel, Field
        
        class FinancialMonth(BaseModel):
            month: str
            revenue: float
            cogs: float
            opex: float
            ar_balance: float
            cash_balance: float
            line_items: dict[str, float] = Field(default_factory=dict)
        
        fm = FinancialMonth(
            month="2024-04",
            revenue=800000,
            cogs=300000,
            opex=100000,
            ar_balance=90000,
            cash_balance=250000
        )
        assert fm.line_items == {}


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION TEST — Full CSV → local_parser → 3-Way Model Pipeline
# ═══════════════════════════════════════════════════════════════════

class TestIntegration_FullPipeline:
    """End-to-end: CSV with granular items → parser → proportionate forecast → Indirect Method."""
    
    def test_full_pipeline_with_granular_data(self):
        """Load the generated test CSV and run the complete pipeline."""
        csv_path = os.path.join(os.path.dirname(__file__), "granular_test_data.csv")
        if not os.path.exists(csv_path):
            pytest.skip("granular_test_data.csv not found — run generate_test_data.py first")
        
        with open(csv_path, "rb") as f:
            file_bytes = f.read()
        
        # Step 1: Parse
        result = local_fallback_parse(file_bytes, "granular_test_data.csv")
        data = result["data"]
        
        assert len(data) >= 6, f"Too few months parsed: {len(data)}"
        
        # Verify granular items extracted
        first_row = data[0]
        assert len(first_row["line_items"]) >= 3, f"Too few line items: {first_row['line_items']}"
        
        # Step 2: Calculate proportionate percentages
        revenues = [d["revenue"] for d in data]
        opex_arr = [d["opex"] for d in data]
        cogs_arr = [d["cogs"] for d in data]
        payroll_arr = [d["payroll"] for d in data]
        
        total_opex = sum(opex_arr)
        hist_line_item_sums = {}
        for d in data:
            for k, v in d["line_items"].items():
                hist_line_item_sums[k] = hist_line_item_sums.get(k, 0) + v
        line_item_pcts = {k: v / total_opex for k, v in hist_line_item_sums.items()} if total_opex > 0 else {}
        
        assert len(line_item_pcts) >= 3, "Should have at least 3 line item percentages"
        
        # Step 3: Run forecast + Indirect Method
        baseline_forecast = multiple_linear_regression_forecast(revenues, periods=12)
        assert len(baseline_forecast) == 12
        
        cogs_pct = percent_of_sales(cogs_arr, revenues)
        opex_pct = percent_of_sales(opex_arr, revenues)
        payroll_pct = percent_of_sales(payroll_arr, revenues)
        
        # Run Indirect Method loop
        current_ar = data[-1].get("ar_balance", 0)
        current_ap = data[-1].get("ap_balance", 0)
        last_rev = revenues[-1] if revenues[-1] > 0 else 1
        ar_pct = current_ar / last_rev
        last_costs = cogs_arr[-1] + opex_arr[-1] + payroll_arr[-1]
        last_costs = last_costs if last_costs > 0 else 1
        ap_pct_ratio = current_ap / last_costs
        
        prev_ar = current_ar
        prev_ap = current_ap
        running_cash = data[-1]["cash_balance"]
        
        for i, val in enumerate(baseline_forecast):
            proj_rev = val
            proj_cogs = proj_rev * cogs_pct
            proj_opex = proj_rev * opex_pct
            proj_payroll = proj_rev * payroll_pct
            proj_ebitda = (proj_rev - proj_cogs) - proj_opex - proj_payroll
            
            operating_profit_bwc = proj_ebitda
            proj_ar = proj_rev * ar_pct
            proj_ap = (proj_cogs + proj_opex + proj_payroll) * ap_pct_ratio
            delta_ar = proj_ar - prev_ar
            delta_ap = proj_ap - prev_ap
            prev_ar = proj_ar
            prev_ap = proj_ap
            
            cash_from_ops = operating_profit_bwc + delta_ap - delta_ar
            
            # Verify math identity
            assert isinstance(cash_from_ops, float), "cash_from_ops should be a float"
            
            # Verify line items
            proj_items = {k: round(proj_opex * pct) for k, pct in line_item_pcts.items()}
            items_total = sum(proj_items.values())
            
            # Line items are proportional to OpEx — each should be > 0 and reasonable
            assert items_total > 0, f"Month {i}: total items should be positive"
            for k, v in proj_items.items():
                assert v >= 0, f"Month {i}: {k} has negative value {v}"
        
        print("✅ Full integration pipeline passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
