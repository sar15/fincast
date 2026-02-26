from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional
import os
import io
import json
import pandas as pd
import numpy as np

from local_parser import local_fallback_parse
from algorithms import (
    calculate_geometric_growth, 
    countback_dso, 
    multiple_linear_regression_forecast,
    percent_of_sales,
    straight_line_forecast,
    compute_advance_tax_schedule,
    INDIAN_FY_MONTHS
)

app = FastAPI(title="FinCast Engine", description="Forecasting Engine with AI Normalization")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "ok"}

@app.post("/api/v1/analyze")
async def analyze_file(
    file: UploadFile = File(...),
    assumptions: Optional[str] = Form(None)
):
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Only CSV or Excel files supported")
        
    contents = await file.read()
    
    # Parse CA Assumptions
    ca_overrides = {}
    if assumptions:
        try:
            ca_overrides = json.loads(assumptions)
        except:
            pass
            
    try:
        # Fallback raw data handler for Tally-style Vouchers
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
            
        columns_lower = [str(c).lower() for c in df.columns]
        
        # Detect if it's a Tally/Transaction export (Debit/Credit/Date) and auto-aggregate to Months
        is_transactional = any("debit" in c or "credit" in c or "dr/cr" in c for c in columns_lower)
        data = []
        
        if is_transactional:
            # We must group by Month and sum Debits vs Credits to get P&L equivalents
            date_col = next((c for c in df.columns if 'date' in str(c).lower()), df.columns[0])
            try:
                # Convert messy dates to periods
                df['month_period'] = pd.to_datetime(df[date_col], errors='coerce').dt.to_period('M')
                df = df.dropna(subset=['month_period'])
                
                # Identify debit vs credit columns
                credit_col = next((c for c in df.columns if 'credit' in str(c).lower()), None)
                debit_col = next((c for c in df.columns if 'debit' in str(c).lower()), None)
                part_col = next((c for c in df.columns if 'particular' in str(c).lower() or 'desc' in str(c).lower()), None)
                
                # Default mapping logic
                if credit_col and debit_col:
                    # Clean the numbers
                    df[credit_col] = pd.to_numeric(df[credit_col].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0)
                    df[debit_col] = pd.to_numeric(df[debit_col].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0)
                    
                    # Group chronologically
                    monthly = df.groupby('month_period').agg({credit_col: 'sum', debit_col: 'sum'}).reset_index()
                    monthly = monthly.sort_values('month_period')
                    
                    # Accumulate cash assuming opening was ~100k or just track delta
                    cash = 100000 
                    
                    for _, row in monthly.iterrows():
                        # Simplification: Credits = Revenue (for SMEs usually), Debits = OpEx/COGS
                        rev = float(row[credit_col])
                        exp = float(row[debit_col])
                        
                        cash = cash + rev - exp
                        data.append({
                            "month": str(row['month_period']),
                            "revenue": rev,
                            "cogs": exp * 0.4, # proxy split 
                            "opex": exp * 0.6,
                            "payroll": 0,
                            "debt_service": 0,
                            "capex": 0,
                            "ap_balance": 0,
                            "ar_balance": rev * 0.15, 
                            "cash_balance": cash
                        })
                else:
                    raise Exception("Missing debit/credit columns in transactional data")
            except Exception as e:
                # If transaction logic fails, fallback to standard NLP parser
                pass

        # If data is still empty (Wasn't transactional, or transactional logic failed)
        if not data:
            structured_data = local_fallback_parse(contents, file.filename)
            data = structured_data["data"]
            
        if len(data) < 3:
            raise HTTPException(status_code=400, detail="Data must contain at least 3 months of explicit chronological data for accurate ML forecasting.")
            
        # Extract and compute timeseries averages for the new deep metrics
        revenues = [d.get("revenue", 0) for d in data]
        cogs_arr = [d.get("cogs", 0) for d in data]
        opex_arr = [d.get("opex", 0) for d in data]
        payroll_arr = [d.get("payroll", 0) for d in data]
        debt_arr = [d.get("debt_service", 0) for d in data]
        capex_arr = [d.get("capex", 0) for d in data]
        
        # We need absolute metrics for the most recent month for the Bridge Analysis
        rm = data[-1]
        
        # Calculate complex KPI Ratios
        geo_growth = calculate_geometric_growth(revenues)
        current_ar = rm.get("ar_balance", 0)
        current_ap = rm.get("ap_balance", 0)
        
        avg_dso = countback_dso(current_ar, list(reversed(revenues)))
        # Simulated DPO = AP / (average COGS/365)
        avg_monthly_cogs = sum(cogs_arr)/len(cogs_arr) if cogs_arr else 0
        calc_dpo = (current_ap / (avg_monthly_cogs * 12)) * 365 if avg_monthly_cogs > 0 else 0
        
        # Calculate profitability
        rm_rev = rm.get("revenue", 0)
        rm_cogs = rm.get("cogs", 0)
        rm_opex = rm.get("opex", 0)
        rm_payroll = rm.get("payroll", 0)
        rm_debt = rm.get("debt_service", 0)
        rm_capex = rm.get("capex", 0)
        
        gross_profit = rm_rev - rm_cogs
        ebitda = gross_profit - rm_opex - rm_payroll
        net_profit = ebitda - rm_debt - rm_capex
        
        gross_margin = (gross_profit / rm_rev * 100) if rm_rev > 0 else 0
        net_margin = (net_profit / rm_rev * 100) if rm_rev > 0 else 0
        
        # --- CA ASSUMPTION SANDBOX OVERRIDES ---
        
        # Run Top-Line Forecast
        try:
            val = str(ca_overrides.get("revenue_growth", "")).strip()
            if val:
                manual_growth = float(val) / 100.0
                baseline_forecast = []
                base = revenues[-1] if revenues else 0
                for _ in range(12):
                    base *= (1 + manual_growth)
                    baseline_forecast.append(max(0, base))
            else:
                baseline_forecast = multiple_linear_regression_forecast(revenues, periods=12)
        except ValueError:
             baseline_forecast = multiple_linear_regression_forecast(revenues, periods=12)
            
        try:
            t_val = str(ca_overrides.get("tax_rate", "")).strip()
            custom_tax_rate = float(t_val) / 100.0 if t_val else 0.15
        except ValueError:
            custom_tax_rate = 0.15
            
        try:
            c_val = str(ca_overrides.get("new_capex", "")).strip()
            custom_capex = float(c_val) if c_val else 0.0
        except ValueError:
            custom_capex = 0.0
        
        # 3-Way Modeling: Predict Operating Expenses via "Percent of Sales" Method
        cogs_pct = percent_of_sales(cogs_arr, revenues)
        opex_pct = percent_of_sales(opex_arr, revenues)
        payroll_pct = percent_of_sales(payroll_arr, revenues)
        
        # Calculate percent of total OpEx for each granular line item
        line_item_pcts = {}
        total_opex_historical = sum(opex_arr)
        if total_opex_historical > 0:
            hist_line_item_sums = {}
            for d in data:
                for k, v in d.get("line_items", {}).items():
                    hist_line_item_sums[k] = hist_line_item_sums.get(k, 0) + v
            for k, total_val in hist_line_item_sums.items():
                line_item_pcts[k] = total_val / total_opex_historical
        
        capex_forecast = straight_line_forecast(capex_arr, periods=12)
        debt_forecast = straight_line_forecast(debt_arr, periods=12)
        
        area_chart_data = []
        three_way_model = []
        
        start_cash = data[-2].get("cash_balance", 0) if len(data) >= 2 else 0
        end_cash = rm.get("cash_balance", 0)
        running_cash = round(end_cash)
        
        # --- PHASE 1: Compute raw EBT for all 12 months (needed for annual tax estimate) ---
        monthly_ebt = []
        for i, val in enumerate(baseline_forecast):
            proj_rev = val
            proj_cogs = proj_rev * cogs_pct
            proj_gp = proj_rev - proj_cogs
            proj_opex = proj_rev * opex_pct
            proj_payroll = proj_rev * payroll_pct
            proj_ebitda = proj_gp - proj_opex - proj_payroll
            proj_debt = debt_forecast[i]
            proj_capex = capex_forecast[i] + (custom_capex / 12)
            proj_net_profit = proj_ebitda - proj_debt - proj_capex
            monthly_ebt.append(proj_net_profit)
        
        # --- PHASE 2: Compute Indian Advance Tax Schedule (Section 211) ---
        # Tax is NOT spread evenly — it hits only in Jun(M3), Sep(M6), Dec(M9), Mar(M12)
        # with statutory percentages: 15%, 30%, 30%, 25% of estimated annual liability
        advance_tax_monthly = compute_advance_tax_schedule(monthly_ebt, custom_tax_rate)
        
        estimated_annual_tax = sum(advance_tax_monthly)
        advance_tax_exempt = estimated_annual_tax < 10000  # Section 208 threshold
        
        # Calculate working capital ratios for Indirect Method Cash Flow
        last_rev = revenues[-1] if revenues and revenues[-1] > 0 else 1
        ar_pct = current_ar / last_rev
        last_costs = (cogs_arr[-1] + opex_arr[-1] + payroll_arr[-1])
        last_costs = last_costs if last_costs > 0 else 1
        ap_pct = current_ap / last_costs
        
        prev_ar = current_ar
        prev_ap = current_ap
        
        # --- PHASE 3: Build the full 3-Way Model with correct tax scheduling ---
        for i, val in enumerate(baseline_forecast):
            proj_rev = val
            proj_cogs = proj_rev * cogs_pct
            proj_gp = proj_rev - proj_cogs
            proj_opex = proj_rev * opex_pct
            proj_payroll = proj_rev * payroll_pct
            proj_ebitda = proj_gp - proj_opex - proj_payroll
            
            proj_debt = debt_forecast[i]
            proj_capex = capex_forecast[i] + (custom_capex / 12)
            
            proj_net_profit = proj_ebitda - proj_debt - proj_capex
            
            # --- INDIRECT METHOD CASH FLOW (Schedule III) ---
            # 1. Operating Profit before Working Capital Changes
            operating_profit_bwc = proj_ebitda
            
            # 2. Adjustments for Working Capital
            proj_ar = proj_rev * ar_pct
            proj_ap = (proj_cogs + proj_opex + proj_payroll) * ap_pct
            
            delta_ar = proj_ar - prev_ar  # Increase in AR is an outflow
            delta_ap = proj_ap - prev_ap  # Increase in AP is an inflow
            
            prev_ar = proj_ar
            prev_ap = proj_ap
            
            # 3. Cash Generated from Operations
            cash_from_operations = operating_profit_bwc + delta_ap - delta_ar
            
            # 4. Less Taxes Paid
            proj_tax = advance_tax_monthly[i]
            net_cash_operating = cash_from_operations - proj_tax
            
            # 5. Cash Flow from Investing
            net_cash_investing = -proj_capex
            
            # 6. Cash Flow from Financing
            net_cash_financing = -proj_debt
            
            # Total Net Cash Flow
            cf_month = net_cash_operating + net_cash_investing + net_cash_financing
            rounded_cf_month = round(cf_month)
            running_cash += rounded_cf_month
            # Use Indian FY month labels (Apr-Mar) instead of generic M1-M12
            month_label = INDIAN_FY_MONTHS[i] if i < len(INDIAN_FY_MONTHS) else f"M{i+1}"
            
            # Forecast Granular Line Items proportional to forecasted OpEx
            proj_line_items = {}
            for k, pct in line_item_pcts.items():
                proj_line_items[k] = round(proj_opex * pct)

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
                "net_cash_flow": rounded_cf_month,
                "ending_cash": running_cash,
                "is_tax_quarter": proj_tax > 0,
                "line_items": proj_line_items
            })
            
            # Store confidence cones for charting
            decay_factor = 1 + (0.02 * i) 
            lower = val * (1 - (0.08 * decay_factor))
            upper = val * (1 + (0.08 * decay_factor))
            area_chart_data.append({
                "month": month_label, 
                "baseline": round(val), 
                "lower": round(max(0, lower)), 
                "upper": round(upper)
            })
            
        start_cash = data[-2].get("cash_balance", 0) if len(data) >= 2 else 0
        end_cash = rm.get("cash_balance", 0)
        
        # Comprehensive Waterfall Bridge for the advanced variables
        waterfall_data = [
            {"name": "Start Cash", "value": round(start_cash), "isTotal": True},
            {"name": "Revenue", "value": round(rm_rev), "isTotal": False},
            {"name": "COGS", "value": round(-rm_cogs), "isTotal": False},
        ]
        
        # Conditionally add rows only if they exist in ledger
        if rm_opex > 0: waterfall_data.append({"name": "OpEx", "value": round(-rm_opex), "isTotal": False})
        if rm_payroll > 0: waterfall_data.append({"name": "Payroll", "value": round(-rm_payroll), "isTotal": False})
        if rm_debt > 0: waterfall_data.append({"name": "Debt / EMI", "value": round(-rm_debt), "isTotal": False})
        if rm_capex > 0: waterfall_data.append({"name": "Capex", "value": round(-rm_capex), "isTotal": False})
        
        calc_adv_tax = round(net_profit * 0.15) if net_profit > 0 else 0
        if calc_adv_tax > 0: waterfall_data.append({"name": "Adv. Tax", "value": -calc_adv_tax, "isTotal": False})
        
        waterfall_data.append({"name": "End Cash", "value": round(end_cash), "isTotal": True})

        return {
            "status": "success",
            "kpis": {
                "projected_12m": round(sum(baseline_forecast)),
                "geo_growth_rate": round(geo_growth * 100, 2),
                "calculated_dso": round(avg_dso, 1),
                "calculated_dpo": round(calc_dpo, 1),
                "gross_margin": round(gross_margin, 2),
                "net_margin": round(net_margin, 2),
                "ebitda": round(ebitda)
            },
            "charts": {
                "areaData": area_chart_data,
                "waterfallData": waterfall_data
            },
            "three_way_model": three_way_model,
            "tax_metadata": {
                "schedule": "Section 211 - Indian Income Tax Act",
                "installments": {
                    "Q1_Jun15": "15% of estimated annual liability",
                    "Q2_Sep15": "30% incremental (45% cumulative)",
                    "Q3_Dec15": "30% incremental (75% cumulative)",
                    "Q4_Mar15": "25% incremental (100% cumulative)"
                },
                "estimated_annual_tax": round(estimated_annual_tax),
                "advance_tax_exempt": advance_tax_exempt,
                "exempt_note": "Section 208: No advance tax required if total liability < ₹10,000" if advance_tax_exempt else None
            }
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Data Extraction Error: {str(e)}")
