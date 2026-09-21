"""Day-count, compounding and bond-pricing conventions used throughout the project.

Conventions (all inferred from, and checked against, the FBIL files -- see README):
  * Valuation date 11-Sep-2026; T+1 business-day settlement -> 15-Sep-2026
    (12/13 Sep are a weekend and 14 Sep 2026 was a market holiday, Ganesh Chaturthi).
    multidate.detect_settlement() finds the same date from FBIL's own prices.
  * Prices published by FBIL are CLEAN prices; dirty = clean + accrued.
  * Semi-annual compounding: DF(t) = (1 + z/2) ** (-2 t), z as a decimal.
  * Year fractions: actual days / 365.25 from the settlement date.
"""
from datetime import date
from dateutil.relativedelta import relativedelta
import numpy as np

VALUATION_DATE = date(2026, 9, 11)
SETTLEMENT_DATE = date(2026, 9, 15)
DAYS_PER_YEAR = 365.25


def yearfrac(d, origin=SETTLEMENT_DATE):
    """Actual/365.25 year fraction between origin and d."""
    return (d - origin).days / DAYS_PER_YEAR


def coupon_schedule(maturity, settle=SETTLEMENT_DATE):
    """Semi-annual coupon dates counted back from maturity.

    Returns (previous_coupon_date, [future coupon dates in ascending order])."""
    future, k, d = [], 0, maturity
    while d > settle:
        future.append(d)
        k += 1
        d = maturity - relativedelta(months=6 * k)
    return d, sorted(future)


def cash_flows(coupon_pct, maturity, settle=SETTLEMENT_DATE, face=100.0):
    """List of (date, amount) future cash flows per 100 face value."""
    _, dates = coupon_schedule(maturity, settle)
    half = coupon_pct / 2.0 * face / 100.0
    return [(d, half + (face if d == maturity else 0.0)) for d in dates]


def accrued_interest(coupon_pct, maturity, settle=SETTLEMENT_DATE):
    """Accrued interest, actual/actual within the coupon period."""
    prev, dates = coupon_schedule(maturity, settle)
    nxt = dates[0]
    w = (nxt - settle).days / (nxt - prev).days
    return coupon_pct / 2.0 * (1.0 - w)


def dirty_from_ytm(coupon_pct, maturity, ytm_pct, settle=SETTLEMENT_DATE):
    """Dirty price from a semi-annual YTM (actual/actual first-period fraction)."""
    prev, dates = coupon_schedule(maturity, settle)
    w = (dates[0] - settle).days / (dates[0] - prev).days
    y = ytm_pct / 200.0
    total = 0.0
    for k, d in enumerate(dates):
        cf = coupon_pct / 2.0 + (100.0 if d == maturity else 0.0)
        total += cf / (1.0 + y) ** (w + k)
    return total


def clean_from_ytm(coupon_pct, maturity, ytm_pct, settle=SETTLEMENT_DATE):
    return dirty_from_ytm(coupon_pct, maturity, ytm_pct, settle) - accrued_interest(coupon_pct, maturity, settle)


def df_semiannual(z_pct, t):
    """Discount factor from a semi-annually compounded zero rate given in percent."""
    return (1.0 + np.asarray(z_pct) / 200.0) ** (-2.0 * np.asarray(t))


def zero_from_df(df, t):
    """Semi-annually compounded zero rate in percent from discount factors."""
    return 200.0 * (np.asarray(df) ** (-1.0 / (2.0 * np.asarray(t))) - 1.0)


def semi_to_annual(z_pct):
    """Convert semi-annual compounded rate (pct) to annual compounded (pct)."""
    return 100.0 * ((1.0 + np.asarray(z_pct) / 200.0) ** 2 - 1.0)
