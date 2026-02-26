import pandas as pd
import io
import re

def clean_numeric(val):
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(',', '').replace('₹', '').replace('$', '').replace('€', '').strip()
    s = re.sub(r'[^\d\.\-]', '', s)
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0

def _get_mapped_column(columns, keywords):
    for col in columns:
        c_lower = str(col).lower()
        if any(kw in c_lower for kw in keywords):
            return col
    return None

def local_fallback_parse(file_bytes: bytes, filename: str) -> dict:
    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes), header=None)
        return _parse_dataframe(df, list(df.columns))
    else:
        # Try all sheets and pick the one that yields the most data
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        best_result = {"data": []}
        for sheet in xls.sheet_names:
            try:
                df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=None)
                result = _parse_dataframe(df, list(df.columns))
                if len(result["data"]) > len(best_result["data"]):
                    best_result = result
            except Exception:
                continue
        return best_result


def _parse_dataframe(df, original_columns) -> dict:

    df = df.dropna(how='all', axis=0).dropna(how='all', axis=1).reset_index(drop=True)
    df_str = df.astype(str).map(lambda x: str(x).lower().strip())

    # Detect horizontal (months in columns usually row 0 or 1)
    horizontal = False
    header_row_idx = 0
    
    for r_idx, row in df_str.iterrows():
        month_count = sum(1 for cell in row if re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4}-\d{2})', cell))
        if month_count >= 3:
            header_row_idx = r_idx
            horizontal = True
            break
            
    if horizontal:
        df.columns = df.iloc[header_row_idx]
        df = df.iloc[header_row_idx+1:].reset_index(drop=True)
        df = df.T
        df.columns = df.iloc[0]
        df = df.iloc[1:].reset_index()
        df.rename(columns={df.columns[0]: 'month_col'}, inplace=True)
    else:
        df.columns = df.iloc[0]
        df = df.iloc[1:].reset_index(drop=True)
        # Dummy date column insertion if none exists
        if not _get_mapped_column(list(df.columns), ['month', 'date', 'period']):
            df.insert(0, 'month_col', df.index)

    # Zoho & Tally Advanced Parameters mapping
    columns = list(df.columns)
    
    # 1. Inflows & Revenue
    rev_col = _get_mapped_column(columns, ['revenue', 'sales', 'turnover', 'income', 'receipts', 'inflow', 'cash in'])
    
    # 2. Outflows & Liabilities
    cogs_col = _get_mapped_column(columns, ['cogs', 'cost of goods', 'cost of sales', 'direct cost', 'direct expense', 'purchases', 'material'])
    opex_col = _get_mapped_column(columns, ['opex', 'operating', 'expenses', 'indirect', 'admin', 'overhead', 'outflow', 'cash out', 'payment'])
    payroll_col = _get_mapped_column(columns, ['salary', 'payroll', 'wages', 'employee', 'pf', 'esi', 'labour'])
    debt_col = _get_mapped_column(columns, ['loan', 'debt', 'emi', 'interest', 'liabilities', 'borrowings'])
    invest_col = _get_mapped_column(columns, ['investment', 'capex', 'fixed asset', 'capital'])
    
    # 3. Liquidity & Working Capital
    ar_col = _get_mapped_column(columns, ['receivable', 'debtor', 'a/r', 'sundry debtor'])
    ap_col = _get_mapped_column(columns, ['payable', 'creditor', 'a/p'])
    cash_col = _get_mapped_column(columns, ['cash', 'bank', 'closing balance', 'liquidity', 'balance'])
    
    date_col = _get_mapped_column(columns, ['month', 'date', 'period']) or 'month_col'

    extracted_data = []

    mapped_cols = {rev_col, cogs_col, opex_col, payroll_col, debt_col, invest_col, ar_col, ap_col, cash_col, date_col}
    unmapped_cols = [c for c in columns if c not in mapped_cols and str(c).strip() != '']

    for idx, row in df.iterrows():
        # Validate row has at least some data
        if pd.isna(row.get(rev_col)) and pd.isna(row.get(opex_col)) and pd.isna(row.get(cash_col)):
            continue
            
        rev_val = clean_numeric(row.get(rev_col)) if rev_col else 0.0
        cogs_val = clean_numeric(row.get(cogs_col)) if cogs_col else 0.0
        opex_val = clean_numeric(row.get(opex_col)) if opex_col else 0.0
        payroll_val = clean_numeric(row.get(payroll_col)) if payroll_col else 0.0
        debt_val = clean_numeric(row.get(debt_col)) if debt_col else 0.0
        invest_val = clean_numeric(row.get(invest_col)) if invest_col else 0.0
        ar_val = clean_numeric(row.get(ar_col)) if ar_col else 0.0
        ap_val = clean_numeric(row.get(ap_col)) if ap_col else 0.0
        cash_val = clean_numeric(row.get(cash_col)) if cash_col else 0.0
        
        month_val = str(row.get(date_col, f"M{idx+1}")).strip()

        # Skip total rows
        if 'total' in month_val.lower() or (rev_val == 0.0 and opex_val == 0.0 and cash_val == 0.0):
            continue

        # Extract granular line items
        line_items = {}
        for col in unmapped_cols:
            val = clean_numeric(row.get(col))
            if val != 0.0:
                # Keep exact column name but title case it for neatness
                clean_name = str(col).strip().title()
                line_items[clean_name] = abs(val)

        extracted_data.append({
            "month": month_val,
            "revenue": abs(rev_val),
            "cogs": abs(cogs_val),
            "payroll": abs(payroll_val),
             # To prevent double-counting if file has both generic 'expenses' and 'payroll', we don't assume. 
             # We just present them raw.
            "opex": abs(opex_val), 
            "debt_service": abs(debt_val),
            "capex": abs(invest_val),
            "ar_balance": abs(ar_val),
            "ap_balance": abs(ap_val),
            "cash_balance": cash_val,
            "line_items": line_items
        })

    return {"data": extracted_data}
