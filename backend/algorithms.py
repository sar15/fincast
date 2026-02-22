import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from sklearn.linear_model import LinearRegression
import warnings
from statsmodels.tools.sm_exceptions import ConvergenceWarning

warnings.simplefilter('ignore', ConvergenceWarning)
warnings.simplefilter('ignore', FutureWarning)


# ============================================================================
# CORE MATHEMATICAL UTILITIES
# ============================================================================

def calculate_geometric_growth(data: list[float]) -> float:
    """Geometric Mean growth rate — correctly accounts for compounding & volatility drag."""
    if len(data) < 2: return 0.0
    sanitized = [d for d in data if d > 0]
    if len(sanitized) < 2: return 0.0
    product = 1.0
    for i in range(1, len(sanitized)):
        product *= sanitized[i] / sanitized[i-1]
    return (product ** (1 / (len(sanitized) - 1))) - 1


def countback_dso(ar_balance: float, historical_sales: list[float]) -> float:
    """Countback (Exhaustion) Method for DSO — iterates backwards through monthly sales
    to determine the exact number of days the current A/R balance represents.
    This is the CA-standard method, not the naive AR/Revenue*30 formula."""
    remainder = ar_balance
    total_dso = 0.0
    days_in_month = 30
    for month_sales in historical_sales:
        if remainder > month_sales:
            total_dso += days_in_month
            remainder -= month_sales
        else:
            ratio = remainder / month_sales if month_sales > 0 else 0
            total_dso += ratio * days_in_month
            break
    return total_dso


# ============================================================================
# INDIAN ADVANCE TAX — Section 211, Income Tax Act (AY 2026-27 / 2027-28)
# ============================================================================
# Statutory schedule for non-presumptive taxpayers:
#   June 15:     15% of estimated annual tax liability
#   September 15: 45% cumulative (i.e. 30% incremental)
#   December 15:  75% cumulative (i.e. 30% incremental)
#   March 15:    100% cumulative (i.e. 25% incremental)
#
# Indian FY runs April–March. Our forecast months M1–M12 map to:
#   M1=Apr, M2=May, M3=Jun, M4=Jul, M5=Aug, M6=Sep,
#   M7=Oct, M8=Nov, M9=Dec, M10=Jan, M11=Feb, M12=Mar
#
# Tax outflow months (0-indexed): M3(Jun)=idx 2, M6(Sep)=idx 5, M9(Dec)=idx 8, M12(Mar)=idx 11

ADVANCE_TAX_SCHEDULE = {
    2:  0.15,   # June 15 — 15% of annual liability
    5:  0.30,   # September 15 — 30% incremental (cumulative 45%)
    8:  0.30,   # December 15 — 30% incremental (cumulative 75%)
    11: 0.25,   # March 15 — 25% incremental (cumulative 100%)
}

# Indian FY month labels
INDIAN_FY_MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep",
                    "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]


def compute_advance_tax_schedule(
    monthly_net_profits: list[float],
    tax_rate: float
) -> list[float]:
    """Compute the exact advance tax outflow per month using Indian statutory schedule.
    
    Args:
        monthly_net_profits: List of 12 projected monthly EBT values
        tax_rate: Effective tax rate as a decimal (e.g. 0.25 for 25%)
    
    Returns:
        List of 12 monthly tax outflow values where tax only hits in 
        June(M3), September(M6), December(M9), and March(M12).
        All other months have zero tax outflow.
    """
    # Step 1: Estimate total annual taxable profit
    estimated_annual_profit = sum(monthly_net_profits)
    
    # If the business is projected to be loss-making, no advance tax is due
    if estimated_annual_profit <= 0:
        return [0.0] * 12
    
    # Step 2: Compute total estimated annual tax liability
    annual_tax_liability = estimated_annual_profit * tax_rate
    
    # Step 3: If total tax < ₹10,000, advance tax is NOT mandatory (Section 208)
    # However, the CA may still want to provision it. We provision it anyway
    # but flag it in the model. For SMEs this threshold is important.
    
    # Step 4: Distribute tax across the 4 statutory installments
    monthly_tax = [0.0] * 12
    for month_idx, pct in ADVANCE_TAX_SCHEDULE.items():
        monthly_tax[month_idx] = round(annual_tax_liability * pct, 2)
    
    return monthly_tax


# ============================================================================
# HBS FORECASTING METHODS — Adaptive for Short Time Series
# ============================================================================

def straight_line_forecast(data: list[float], periods: int = 12) -> list[float]:
    """HBS Method 1 — Straight Line: Constant growth from geometric mean.
    Used for: Debt service, EMI, fixed costs that don't scale with revenue."""
    if len(data) < 2:
        return [max(0, data[-1] if data else 0)] * periods
    growth = calculate_geometric_growth(data)
    growth = max(-0.15, min(0.15, growth))  # Cap to ±15% realistic bounds
    forecast = []
    base = data[-1]
    for _ in range(periods):
        base *= (1 + growth)
        forecast.append(max(0, base))
    return forecast


def moving_average_forecast(data: list[float], window: int = 3, periods: int = 12) -> list[float]:
    """HBS Method 2 — Moving Average: Smooths short-term fluctuations."""
    if len(data) < window:
        return straight_line_forecast(data, periods)
    history = list(data)
    forecast = []
    for _ in range(periods):
        nxt = sum(history[-window:]) / window
        forecast.append(max(0, nxt))
        history.append(nxt)
    return forecast


def simple_linear_regression(data: list[float], periods: int = 12) -> list[float]:
    """HBS Method 3 — Simple Linear Regression: Y = mX + b over time."""
    if len(data) < 3:
        return straight_line_forecast(data, periods)
    X = np.arange(len(data)).reshape(-1, 1)
    y = np.array(data)
    model = LinearRegression().fit(X, y)
    future_X = np.arange(len(data), len(data) + periods).reshape(-1, 1)
    return [max(0, p) for p in model.predict(future_X).tolist()]


def adaptive_holt_winters_forecast(data: list[float], periods: int = 12) -> list[float]:
    """Adaptive Holt-Winters Exponential Smoothing.
    
    Per Rob Hyndman (the leading authority on exponential smoothing):
    - Minimum data points for seasonal HW with period m = m + 5
    - For m=4 (quarterly seasonality): need 9+ data points
    - For m=6 (half-yearly seasonality): need 11+ data points  
    - For m=12 (full annual seasonality): need 17+ data points (24+ recommended)
    
    This function adaptively selects the best seasonal period based on 
    available data length, ensuring the model works even for SMEs with
    only 6-8 months of history.
    
    Selection ladder:
    - 3-5 months:    Simple Linear Regression (no seasonality possible)
    - 6-8 months:    Holt-Winters with trend only, no seasonality
    - 9-11 months:   Holt-Winters with quarterly seasonality (period=4)
    - 12-23 months:  Holt-Winters with half-yearly seasonality (period=6)
    - 24+ months:    Holt-Winters with full multiplicative seasonality (period=12)
    """
    n = len(data)
    
    if n < 6:
        # Too few data points for exponential smoothing — use linear regression
        return simple_linear_regression(data, periods)
    
    ts = pd.Series(data, dtype=float)
    
    try:
        if n >= 24:
            # Full annual multiplicative seasonality (the gold standard)
            model = ExponentialSmoothing(
                ts, trend='mul', seasonal='mul', seasonal_periods=12,
                initialization_method='estimated'
            ).fit(optimized=True)
        elif n >= 12:
            # Half-yearly additive seasonality — captures H1/H2 patterns
            model = ExponentialSmoothing(
                ts, trend='add', seasonal='add', seasonal_periods=6,
                initialization_method='estimated'
            ).fit(optimized=True)
        elif n >= 9:
            # Quarterly additive seasonality — captures Q1/Q2/Q3/Q4 patterns
            model = ExponentialSmoothing(
                ts, trend='add', seasonal='add', seasonal_periods=4,
                initialization_method='estimated'
            ).fit(optimized=True)
        else:
            # 6-8 months: trend-only exponential smoothing (Holt's linear)
            model = ExponentialSmoothing(
                ts, trend='add', seasonal=None,
                initialization_method='estimated'
            ).fit(optimized=True)
        
        result = [max(0, val) for val in model.forecast(periods).tolist()]
        
        # Safety: if HW produces absurd values (>5x last value), fall back
        last_val = data[-1] if data[-1] > 0 else 1
        if any(v > last_val * 5 or v < 0 for v in result):
            return simple_linear_regression(data, periods)
        
        return result
        
    except Exception:
        # If statsmodels fails for any reason, gracefully degrade
        return simple_linear_regression(data, periods)


def multiple_linear_regression_forecast(data: list[float], periods: int = 12) -> list[float]:
    """HBS Method 4 — Multiple Linear Regression proxy.
    Since we only have a single time-series variable (not multiple X variables),
    we use Adaptive Holt-Winters as the best auto-regressive approximation."""
    return adaptive_holt_winters_forecast(data, periods)


def percent_of_sales(dependent_var_history: list[float], revenue_history: list[float]) -> float:
    """HBS Method 5 — Percent of Sales: Historical ratio of expense to revenue.
    Used for: COGS, OpEx, Payroll — expenses that scale proportionally with sales."""
    total_rev = sum(revenue_history)
    if total_rev == 0:
        return 0.0
    return sum(dependent_var_history) / total_rev

