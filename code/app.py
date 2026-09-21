"""End-to-end application: data -> ZCYC -> comparison with FBIL -> STRIPS, in one command.

    python app.py                                 reproduce everything (all scripts, in order)
    python app.py --date 2026-08-21               one date: curve, comparison and HTML report
    python app.py --date 2026-09-11 --sdl IN2020250089    ... plus STRIPS of an SDL

The single-date mode writes additional_material/outputs/app/<date>/ with
    zcyc_<date>.csv            zero (semi-annual and annualised), par yield, discount factor, FBIL gap
    strips_<isin>.csv          one row per STRIP (only with --sdl)
    report_<date>.html         self-contained report with the charts and tables
Input files for the date must be in input_data/multi/ (gsec_valuation_, gsec_zcyc_and_strips_, tbill_).
"""
import argparse
import base64
import io
import json
import os
import subprocess
import sys
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
warnings.filterwarnings("ignore")
import multidate as md   # noqa: E402
import engine as en      # noqa: E402
import strips as sp      # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "additional_material", "outputs")
STEPS = ["tune_and_checks.py", "run_all.py", "run_multidate.py", "run_strips.py"]


def run_everything():
    for step in STEPS:
        print(f"\n=== {step}")
        subprocess.run([sys.executable, os.path.join(HERE, step)], check=True)
    print("\nAll outputs regenerated in additional_material/outputs/. "
          "Rebuild the deck with: node additional_material/deck_source/build_deck.js")


def fig_b64(fig):
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=130, bbox_inches="tight"); plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def one_date(iso, sdl_isin=None):
    params = json.load(open(os.path.join(OUT, "tuned_params.json")))
    out = os.path.join(OUT, "app", iso); os.makedirs(out, exist_ok=True)

    # 1. data
    settle, _ = md.detect_settlement(iso)
    g, tb, z, par = md.load_gsec(iso), md.load_tbills(iso), md.load_zcyc(iso), md.load_par(iso)
    inp = g[g["is_input"] & ~g["is_frb"]]
    # 2. curves
    c_sm, info = en.ls_fit(inp, tb, settle, lam=params["lam"], lam_slope=params["slope"])
    c_ex, _ = en.bootstrap(inp, tb, settle, use_3m=True)
    grid = z["tenor"].to_numpy(float)
    zs = c_sm.zero(grid)
    tab = pd.DataFrame({"tenor_years": grid, "zero_semi_pct": zs, "zero_annual_pct": en.semi_to_annual(zs),
                        "par_semi_pct": en.par_yield(c_sm, grid), "discount_factor": c_sm.df(grid),
                        "fbil_zero_semi_pct": z["zero_semi"].to_numpy(float)})
    tab["gap_bp"] = (tab.zero_semi_pct - tab.fbil_zero_semi_pct) * 100
    tab.round(6).to_csv(os.path.join(out, f"zcyc_{iso}.csv"), index=False)
    # 3. comparison
    q_sm, q_ex = en.score(c_sm, z), en.score(c_ex, z)

    fig, ax = plt.subplots(2, 1, figsize=(9, 6), gridspec_kw={"height_ratios": [2.2, 1]}, sharex=True)
    ax[0].plot(grid, tab.fbil_zero_semi_pct, color="#1F3A5F", lw=2.2, label="FBIL ZCYC")
    ax[0].plot(grid, zs, color="#E07B39", ls="--", lw=1.6, label="Smoothed fit")
    ax[0].plot(grid, c_ex.zero(grid), color="#8A8F98", ls=":", lw=1.2, label="Exact-fit bootstrap")
    bt = [md.yearfrac(m, settle) for m in inp.sort_values("maturity")["maturity"]]
    ax[0].scatter(bt, inp.sort_values("maturity")["ytm"], s=16, color="#2A9D8F", label="Input bond YTMs")
    ax[0].set_ylabel("Zero rate, semi-annual (%)"); ax[0].legend(frameon=False, fontsize=8)
    ax[1].plot(grid, tab.gap_bp, color="#E07B39"); ax[1].axhline(0, color="#8A8F98", lw=0.8)
    ax[1].set_ylabel("Gap to FBIL (bp)"); ax[1].set_xlabel("Tenor (years)")
    charts = [fig_b64(fig)]

    # 4. STRIPS (optional)
    strips_html = ""
    if sdl_isin:
        f_sdl = os.path.join(ROOT, "input_data", f"sdl_valuation_{iso}.xlsx")
        if not os.path.exists(f_sdl):
            raise SystemExit(f"No SDL valuation file for {iso} ({f_sdl})")
        s = pd.read_excel(f_sdl, sheet_name="SDL", header=4)
        s.columns = ["isin", "description", "coupon", "maturity", "price", "ytm"]
        s = s.dropna(subset=["isin"]); s["maturity"] = pd.to_datetime(s["maturity"]).dt.date
        b = s[s["isin"] == sdl_isin]
        if b.empty:
            raise SystemExit(f"{sdl_isin} not found in {f_sdl}")
        b = b.iloc[0]
        if not (b.maturity.day == 2 and b.maturity.month in (1, 7)):
            print("Warning: coupon dates are not 2 Jan / 2 Jul, so the RBI guidelines would not treat it as strippable.")
        dirty = float(b.price + md.accrued(b.coupon, b.maturity, settle))
        cfs = [(d, b.coupon / 2.0) for d, _ in md.cash_flows(b.coupon, b.maturity, settle)] + [(b.maturity, 100.0)]
        face = np.r_[np.full(len(cfs) - 1, b.coupon / 2.0), 100.0]
        st, factor = sp.price_strips(cfs, lambda t: c_sm.zero(np.asarray(t, float)), dirty, settle=settle,
                                     time_fn=lambda d: md.yearfrac(d, settle))
        st["strip_type"] = ["Coupon"] * (len(st) - 1) + ["Principal"]
        st["price_per_100_face"] = 100 * st["normalised_value"] / face
        st["implied_yield_semi_pct"] = sp.strip_yield_from_price(st["price_per_100_face"].to_numpy(), st["t_years"].to_numpy())
        st.round(6).to_csv(os.path.join(out, f"strips_{sdl_isin}.csv"), index=False)
        strips_html = (f"<h2>STRIPS of {b.description} ({sdl_isin})</h2><p>Dirty price {dirty:.4f}; sum of PVs "
                       f"{st.pv_unnormalised.sum():.4f}; normalisation factor {factor:.5f}; {len(st) - 1} coupon STRIPS "
                       f"+ 1 principal STRIP. Full table: strips_{sdl_isin}.csv</p>"
                       + st[["date", "strip_type", "t_years", "zero_pct", "pv_unnormalised", "normalised_value",
                             "price_per_100_face", "implied_yield_semi_pct"]].round(4).to_html(index=False))

    keyt = tab[tab.tenor_years.isin([0.25, 0.5, 1, 2, 3, 5, 7, 10, 14, 20, 30, 40, 50])].round(3)
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>ZCYC {iso}</title>
<style>body{{font-family:Calibri,Arial,sans-serif;max-width:960px;margin:24px auto;color:#0F2A33}}
table{{border-collapse:collapse;font-size:13px}}td,th{{border:1px solid #D5E3E5;padding:3px 8px;text-align:right}}
th{{background:#1B6F7A;color:#fff}}</style></head><body>
<h1>Zero coupon yield curve, {iso}</h1>
<p>Settlement {settle} (detected from FBIL's prices). {len(inp)} FBIL input bonds and the 7-day, 3M, 6M and 12M T-bill rates.
Smoothing parameters lambda = {params['lam']}, slope = {params['slope']}.</p>
<h2>Gap to FBIL's published ZCYC (bp)</h2>
<table><tr><th>Curve</th><th>All tenors</th><th>up to 14y</th><th>beyond 14y</th><th>worst</th></tr>
<tr><td>Smoothed fit</td><td>{q_sm['mae']:.2f}</td><td>{q_sm['mae_le14']:.2f}</td><td>{q_sm['mae_gt14']:.2f}</td><td>{q_sm['max']:.2f}</td></tr>
<tr><td>Exact-fit bootstrap</td><td>{q_ex['mae']:.2f}</td><td>{q_ex['mae_le14']:.2f}</td><td>{q_ex['mae_gt14']:.2f}</td><td>{q_ex['max']:.2f}</td></tr></table>
<img style="width:100%" src="data:image/png;base64,{charts[0]}">
<h2>Key tenors (full 200-tenor table: zcyc_{iso}.csv)</h2>{keyt.to_html(index=False)}
{strips_html}</body></html>"""
    path = os.path.join(out, f"report_{iso}.html")
    open(path, "w", encoding="utf-8").write(html)
    print(f"{iso}: smoothed gap {q_sm['mae']:.2f} bp (exact fit {q_ex['mae']:.2f} bp). Report: {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="valuation date, e.g. 2026-09-11 (omit to reproduce everything)")
    ap.add_argument("--sdl", help="ISIN of an SDL to strip (needs input_data/sdl_valuation_<date>.xlsx)")
    a = ap.parse_args()
    if a.date:
        one_date(a.date, a.sdl)
    else:
        run_everything()
