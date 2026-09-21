"""Date-aware loading + settlement detection for the multi-date study (data/multi/)."""
import os
from datetime import date, timedelta

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MULTI = os.path.join(ROOT, "input_data", "multi")
UPLOADED = os.path.join(ROOT, "input_data", "uploaded")   # dates entered through the app


def _find(name):
    """Path of a per-date file: the study folder first, then the folder for dates entered through the app."""
    for folder in (MULTI, UPLOADED):
        p = os.path.join(folder, name)
        if os.path.exists(p):
            return p
    return os.path.join(MULTI, name)


DATES = ["2026-08-05", "2026-08-14", "2026-08-21", "2026-08-28", "2026-09-11"]
DAYS_PER_YEAR = 365.25


# ------------------------------------------------------------------ conventions, parameterised by date
def coupon_schedule(maturity, settle):
    future, k, d = [], 0, maturity
    while d > settle:
        future.append(d)
        k += 1
        d = maturity - relativedelta(months=6 * k)
    return d, sorted(future)


def cash_flows(coupon_pct, maturity, settle, face=100.0):
    _, ds = coupon_schedule(maturity, settle)
    return [(d, coupon_pct / 2.0 + (face if d == maturity else 0.0)) for d in ds]


def accrued(coupon_pct, maturity, settle):
    prev, ds = coupon_schedule(maturity, settle)
    return coupon_pct / 2.0 * (1.0 - (ds[0] - settle).days / (ds[0] - prev).days)


def dirty_from_ytm(coupon_pct, maturity, ytm_pct, settle):
    prev, ds = coupon_schedule(maturity, settle)
    w = (ds[0] - settle).days / (ds[0] - prev).days
    y = ytm_pct / 200.0
    return sum((coupon_pct / 2.0 + (100.0 if d == maturity else 0.0)) / (1.0 + y) ** (w + k)
               for k, d in enumerate(ds))


def clean_from_ytm(coupon_pct, maturity, ytm_pct, settle):
    return dirty_from_ytm(coupon_pct, maturity, ytm_pct, settle) - accrued(coupon_pct, maturity, settle)


def yearfrac(d, settle):
    return (d - settle).days / DAYS_PER_YEAR


# ------------------------------------------------------------------ loaders
def load_gsec(iso):
    g = pd.read_excel(_find(f"gsec_valuation_{iso}.xlsx"), sheet_name="G-Sec", header=4)
    g.columns = ["isin", "coupon", "maturity", "price", "ytm", "remark1", "remark2", "status"][:len(g.columns)]
    g = g.dropna(subset=["isin"]).copy()
    g["maturity"] = pd.to_datetime(g["maturity"]).dt.date
    g["is_frb"] = g["remark1"].eq("FRB")
    g["is_input"] = g["remark1"].eq("Input Point")
    g["input_status"] = g["status"].where(g["is_input"]) if "status" in g else None
    return g.reset_index(drop=True)


def load_par(iso):
    p = pd.read_excel(_find(f"gsec_valuation_{iso}.xlsx"), sheet_name="Par Yield", header=4)
    p.columns = ["tenor", "par_semi", "par_annual"]
    return p.dropna(subset=["tenor"])


def load_zcyc(iso):
    z = pd.read_excel(_find(f"gsec_zcyc_and_strips_{iso}.xlsx"), sheet_name="ZCYC", header=4)
    z.columns = ["tenor", "zero_semi", "zero_annual"]
    return z.dropna(subset=["tenor"])


def load_strips(iso):
    raw = pd.read_excel(_find(f"gsec_zcyc_and_strips_{iso}.xlsx"), sheet_name="STRIPS", header=None)
    raw.columns = ["isin", "name", "maturity", "price", "yield_semi", "remarks"]
    raw["maturity"] = pd.to_datetime(raw["maturity"], errors="coerce")
    s = raw.dropna(subset=["maturity"]).copy()
    s["price"] = pd.to_numeric(s["price"], errors="coerce")
    s["yield_semi"] = pd.to_numeric(s["yield_semi"], errors="coerce")
    s = s.dropna(subset=["price", "yield_semi"])
    s["maturity"] = s["maturity"].dt.date
    return s.reset_index(drop=True)


def load_tbills(iso):
    return pd.read_csv(_find(f"tbill_{iso}.csv"))


# ------------------------------------------------------------------ settlement date, detected not assumed
def detect_settlement(iso, max_ahead=6):
    """Pick the settlement date that best reproduces FBIL's published clean prices from its YTMs."""
    val = date.fromisoformat(iso)
    g = load_gsec(iso)
    g = g[~g["is_frb"]]
    best, rows = None, []
    for k in range(0, max_ahead + 1):
        s = val + timedelta(days=k)
        if s.weekday() >= 5:
            continue
        try:
            err = np.array([clean_from_ytm(r.coupon, r.maturity, r.ytm, s) - r.price
                            for r in g.itertuples() if r.maturity > s + timedelta(days=200)])
        except Exception:
            continue
        rows.append((s, float(np.abs(err).mean() * 100), float(np.abs(err).max() * 100)))
        if best is None or rows[-1][1] < best[1]:
            best = rows[-1]
    return best[0], pd.DataFrame(rows, columns=["settle", "mean_paise", "max_paise"])
