"""STRIPS pricing following the RBI 'Guidelines on Stripping/Reconstitution of G-Secs'.

Guidelines (paras 12-15, Annex 4):
  1. STRIPS are zero-coupon: value each coupon / principal cash flow at a market-based rate, or
     (if no traded zero rates) the published ZCYC:  PV_i = CF_i / (1+z_i/2)^(2 t_i).
  2. Stripping must not create profit or loss, so the STRIPS values are NORMALISED:
        factor = min(book value, market value of the security) / sum(PV_i)
        normalised value_i = factor * PV_i
     so that the sum of STRIPS values equals the value of the security that is extinguished.
"""
import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline

import conventions as cv


# --------------------------------------------------------------------------------------------
# Interpolating FBIL's published (quarterly, 2-decimal) zero curve
# --------------------------------------------------------------------------------------------
def published_curve(zcyc_df, method="cubic"):
    """Return f(t) -> semi-annual zero rate (pct) interpolated from FBIL's published ZCYC."""
    t, z = zcyc_df["tenor"].to_numpy(float), zcyc_df["zero_semi"].to_numpy(float)
    if method == "linear":
        return lambda x: np.interp(np.asarray(x, float), t, z)
    spl = CubicSpline(t, z, bc_type="natural", extrapolate=True)
    lo = t[0]
    # below the first published tenor (0.25y) hold the first rate flat (short-dated STRIPS only)
    return lambda x: np.where(np.asarray(x, float) < lo, z[0], spl(np.asarray(x, float)))


def strip_yield_from_price(price, t):
    return 200.0 * ((100.0 / price) ** (1.0 / (2.0 * t)) - 1.0)


# --------------------------------------------------------------------------------------------
# Core pricing + normalisation
# --------------------------------------------------------------------------------------------
def price_strips(cash_flows, zero_fn, market_value, book_value=None, settle=cv.SETTLEMENT_DATE,
                 time_fn=None):
    """PV each cash flow on the zero curve, then normalise to min(book, market) value.

    cash_flows : list of (date, amount) per 100 face of parent
    zero_fn    : t -> semi-annual zero rate (pct)
    Returns (DataFrame, factor)."""
    time_fn = time_fn or (lambda d: cv.yearfrac(d, settle))
    dates = [d for d, _ in cash_flows]
    cf = np.array([a for _, a in cash_flows])
    t = np.array([time_fn(d) for d in dates])
    z = np.asarray(zero_fn(t), float)
    df = cv.df_semiannual(z, t)
    pv = cf * df
    target = market_value if book_value is None else min(book_value, market_value)
    factor = target / pv.sum()
    out = pd.DataFrame({"date": dates, "t_years": t, "cash_flow": cf, "zero_pct": z, "discount_factor": df,
                        "pv_unnormalised": pv, "normalised_value": factor * pv})
    return out, factor


# --------------------------------------------------------------------------------------------
# Reproduce the worked example in Annex 4 of the guidelines
# --------------------------------------------------------------------------------------------
ANNEX4_ZCYC = [4.0683, 4.6948, 5.3212, 5.6128, 5.9044, 6.1339, 6.3633, 6.4744, 6.5855, 6.7227, 6.8599, 6.9971, 7.1343]
ANNEX4_PV = [6.0274, 5.8711, 5.6841, 5.5055, 5.3174, 5.1305, 4.9392, 4.7663, 4.5946, 4.4187, 4.2439, 4.0707, 67.3029]
ANNEX4_NORM = [5.6564, 5.5098, 5.3343, 5.1666, 4.9901, 4.8147, 4.6352, 4.4730, 4.3118, 4.1467, 3.9827, 3.8201, 63.1606]


def annex4_check():
    """Annex 4 uses whole half-year periods (t = 0.5, 1.0, ... 6.5) for the STRIPS of the 12.30% 2016."""
    cf = np.array([6.15] * 12 + [106.15])
    t = 0.5 * np.arange(1, 14)
    z = np.array(ANNEX4_ZCYC)
    pv = cf * cv.df_semiannual(z, t)
    factor = min(120.0, 129.96) / pv.sum()
    norm = factor * pv
    df = pd.DataFrame({"t": t, "cash_flow": cf, "zcyc": z, "pv_calc": pv, "pv_annex": ANNEX4_PV,
                       "norm_calc": norm, "norm_annex": ANNEX4_NORM})
    df["pv_diff"] = df.pv_calc - df.pv_annex
    df["norm_diff"] = df.norm_calc - df.norm_annex
    return df, factor, pv.sum(), norm.sum()
