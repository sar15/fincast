import pandas as pd
import numpy as np

np.random.seed(42)

months = pd.date_range(start="2021-04-01", periods=36, freq="MS").strftime("%b-%y").tolist()

revenue = []
cogs = []
opex = []
payroll = []
ar = []
ap = []
cash = []

base_rev = 100000
trend = 1500  # $1.5k growth per month
seasonality = [0.9, 0.95, 1.0, 1.1, 1.25, 1.3, 1.2, 1.05, 0.95, 0.85, 0.9, 0.9] # Summer peak

current_cash = 50000

for i in range(36):
    month_idx = i % 12
    # Revenue: Base + Trend + Seasonality + Noise
    r = base_rev + (trend * i)
    r = r * seasonality[month_idx]
    r = r + np.random.normal(0, 5000)
    
    # Costs
    c = r * np.random.uniform(0.35, 0.40) # COGS 35-40%
    p = r * np.random.uniform(0.18, 0.22) # Payroll ~20%
    o = r * np.random.uniform(0.10, 0.15) # Opex ~10-15%
    
    # Working capital
    ar_bal = r * 1.2  # ~35 days DSO
    ap_bal = c * 0.8  # ~24 days DPO
    
    # Cash flow (simplified)
    # We won't make it perfectly balance, just need reasonable looking numbers
    current_cash += (r - c - p - o) * 0.8 # Rough cash conversion
    
    revenue.append(max(0, round(r)))
    cogs.append(max(0, round(c)))
    payroll.append(max(0, round(p)))
    opex.append(max(0, round(o)))
    ar.append(max(0, round(ar_bal)))
    ap.append(max(0, round(ap_bal)))
    cash.append(max(0, round(current_cash)))

df = pd.DataFrame({
    'Month': months,
    'Revenue': revenue,
    'COGS': cogs,
    'Payroll': payroll,
    'OPEX': opex,
    'Receivable': ar,
    'Payable': ap,
    'Cash Balance': cash
})

df.to_csv("good_indian_sme_data.csv", index=False)
print("CSV generated: good_indian_sme_data.csv")
