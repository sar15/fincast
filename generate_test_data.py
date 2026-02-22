"""
Generate a realistic Indian SME CSV with GRANULAR LINE ITEMS
to test the full Schedule III pipeline (Steps 1-4).
"""
import pandas as pd
import numpy as np

np.random.seed(42)

months = pd.date_range(start="2024-04-01", periods=12, freq="MS").strftime("%b-%y").tolist()

revenue = []
cogs = []
opex = []
payroll = []
ar = []
ap = []
cash = []

# Granular line items — these should survive the local_parser unmapped columns logic
marketing = []
rent = []
software = []
office_supplies = []
travel = []

base_rev = 800000
trend = 20000
seasonality = [0.9, 0.95, 1.0, 1.1, 1.25, 1.3, 1.2, 1.05, 0.95, 0.85, 0.9, 0.9]

current_cash = 250000

for i in range(12):
    month_idx = i % 12
    r = base_rev + (trend * i)
    r = r * seasonality[month_idx]
    r = r + np.random.normal(0, 15000)

    c = r * np.random.uniform(0.35, 0.40)
    p = r * np.random.uniform(0.18, 0.22)
    o = r * np.random.uniform(0.10, 0.15)
    
    # Granular expenses (these should NOT get mapped by _get_mapped_column)
    mkt = r * np.random.uniform(0.03, 0.05)
    rnt = np.random.uniform(45000, 55000)  # Fixed rent
    sw  = np.random.uniform(15000, 25000)  # SaaS subscriptions  
    ofs = np.random.uniform(5000, 12000)   # Office supplies
    trv = r * np.random.uniform(0.01, 0.02)  # Travel scales with biz

    ar_bal = r * 1.2
    ap_bal = c * 0.8

    current_cash += (r - c - p - o - mkt - rnt - sw - ofs - trv) * 0.8

    revenue.append(max(0, round(r)))
    cogs.append(max(0, round(c)))
    payroll.append(max(0, round(p)))
    opex.append(max(0, round(o)))
    marketing.append(max(0, round(mkt)))
    rent.append(max(0, round(rnt)))
    software.append(max(0, round(sw)))
    office_supplies.append(max(0, round(ofs)))
    travel.append(max(0, round(trv)))
    ar.append(max(0, round(ar_bal)))
    ap.append(max(0, round(ap_bal)))
    cash.append(max(0, round(current_cash)))

df = pd.DataFrame({
    'Month': months,
    'Revenue': revenue,
    'COGS': cogs,
    'Payroll': payroll,
    'OPEX': opex,
    'Marketing': marketing,
    'Rent': rent,
    'Software Subscriptions': software,
    'Office Supplies': office_supplies,
    'Travel': travel,
    'Receivable': ar,
    'Payable': ap,
    'Cash Balance': cash
})

df.to_csv("granular_test_data.csv", index=False)
print("✅ Generated: granular_test_data.csv")
print(f"   Months: {len(months)}")
print(f"   Columns: {list(df.columns)}")
print(f"   Granular items: Marketing, Rent, Software Subscriptions, Office Supplies, Travel")
print(df.head(3).to_string())
