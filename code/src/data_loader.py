"""Loaders for the FBIL files downloaded for 11-Sep-2026 (see data/)."""
import os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "input_data")
F_GSEC = os.path.join(DATA, "gsec_valuation_2026-09-11.xlsx")
F_SDL = os.path.join(DATA, "sdl_valuation_2026-09-11.xlsx")
F_SDL_ZCYC = os.path.join(DATA, "sdl_zcyc_2026-09-11.xlsx")
F_GSEC_ZCYC = os.path.join(DATA, "gsec_zcyc_and_strips_2026-09-11.xlsx")
F_TBILL = os.path.join(DATA, "tbill_rates_2026-09-11.csv")


def load_gsec():
    """FBIL G-Sec prices/yields. Adds is_frb, is_input (FBIL-flagged input point), input_status."""
    g = pd.read_excel(F_GSEC, sheet_name="G-Sec", header=4)
    g.columns = ["isin", "coupon", "maturity", "price", "ytm", "remark1", "remark2", "status"]
    g = g.dropna(subset=["isin"]).copy()
    g["maturity"] = pd.to_datetime(g["maturity"]).dt.date
    g["is_frb"] = g["remark1"].eq("FRB")
    g["is_input"] = g["remark1"].eq("Input Point")
    g["input_status"] = g["status"].where(g["is_input"])  # 'T' = traded, 'Proxy'
    return g.drop(columns=["remark1", "remark2", "status"]).reset_index(drop=True)


def load_gsec_par():
    p = pd.read_excel(F_GSEC, sheet_name="Par Yield", header=4)
    p.columns = ["tenor", "par_semi", "par_annual"]
    return p


def load_gsec_zcyc():
    z = pd.read_excel(F_GSEC_ZCYC, sheet_name="ZCYC", header=4)
    z.columns = ["tenor", "zero_semi", "zero_annual"]
    return z


def load_strips():
    raw = pd.read_excel(F_GSEC_ZCYC, sheet_name="STRIPS", header=None)
    raw.columns = ["isin", "name", "maturity", "price", "yield_semi", "remarks"]
    raw["maturity"] = pd.to_datetime(raw["maturity"], errors="coerce")
    s = raw.dropna(subset=["maturity"]).copy()
    s["price"] = pd.to_numeric(s["price"])
    s["yield_semi"] = pd.to_numeric(s["yield_semi"])
    s["maturity"] = s["maturity"].dt.date
    s["kind"] = s["name"].str[:2]  # CS coupon strip, PS principal strip
    return s.drop(columns="remarks").reset_index(drop=True)


def load_tbills():
    return pd.read_csv(F_TBILL)


def load_sdl():
    s = pd.read_excel(F_SDL, sheet_name="SDL", header=4)
    s.columns = ["isin", "description", "coupon", "maturity", "price", "ytm"]
    s = s.dropna(subset=["isin"]).copy()
    s["maturity"] = pd.to_datetime(s["maturity"]).dt.date
    return s.reset_index(drop=True)


def load_sdl_zcyc():
    z = pd.read_excel(F_SDL_ZCYC, header=4)
    z.columns = ["tenor", "zero_semi", "zero_annual"]
    return z
