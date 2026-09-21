"""Single-date analysis for 11-Sep-2026:   python run_all.py   (after tune_and_checks.py)

1. Load FBIL inputs                       2. Check conventions against FBIL's own outputs
3. Exact-fit bootstrap + variants         4. Submitted smoothed curve, both scored against FBIL
5. Input-bond diagnostics                 6. Tables, charts, outputs/results_summary.json
Settlement is 15-Sep-2026 (T+1 business day; 14 Sep was a market holiday) and is cross-checked
against multidate.detect_settlement().
"""
import json
import os
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

import conventions as cv          # noqa: E402
import curve as cu                # noqa: E402
import data_loader as dl          # noqa: E402
import engine as en               # noqa: E402
import multidate as md            # noqa: E402
import strips as sp               # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "additional_material", "outputs")
TAB, CH = os.path.join(OUT, "tables"), os.path.join(OUT, "charts")
os.makedirs(TAB, exist_ok=True); os.makedirs(CH, exist_ok=True)
P = json.load(open(os.path.join(OUT, "tuned_params.json")))
ISO = "2026-09-11"

NAVY, ORANGE, TEAL, GREY, RED = "#1F3A5F", "#E07B39", "#2A9D8F", "#8A8F98", "#C0392B"
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "figure.dpi": 100, "savefig.dpi": 190})
S = {}
save = lambda df, name: df.to_csv(os.path.join(TAB, name), index=False)

# ------------------------------------------------------------------ 1. load
SETTLE = cv.SETTLEMENT_DATE
detected, _ = md.detect_settlement(ISO)
assert detected == SETTLE, f"settlement mismatch: conventions {SETTLE}, detected {detected}"
gsec, tbills, fb_z = dl.load_gsec(), dl.load_tbills(), dl.load_gsec_zcyc()
fb_par, strips_fbil, sdl_z = dl.load_gsec_par(), dl.load_strips(), dl.load_sdl_zcyc()
fixed = gsec[~gsec["is_frb"]].copy()
inputs = fixed[fixed["is_input"]].copy()
grid = fb_z["tenor"].to_numpy(float)
fb_zero = fb_z["zero_semi"].to_numpy(float)
S.update(settlement=str(SETTLE), n_gsec_fixed=len(fixed), n_frb=int(gsec["is_frb"].sum()), n_inputs=len(inputs),
         n_inputs_traded=int((inputs["input_status"] == "T").sum()),
         n_inputs_proxy=int((inputs["input_status"] == "Proxy").sum()))

# ------------------------------------------------------------------ 2. convention checks
checks = []
err = np.array([cv.clean_from_ytm(r.coupon, r.maturity, r.ytm) - r.price for r in fixed.itertuples()])
err_t0 = np.array([cv.clean_from_ytm(r.coupon, r.maturity, r.ytm, cv.VALUATION_DATE) - r.price for r in fixed.itertuples()])
checks.append(("Clean prices at T+1 settlement (15-Sep-2026)",
               f"mean |error| {np.abs(err).mean()*100:.2f} paise, max {np.abs(err).max()*100:.2f} "
               f"(settling on 11-Sep instead: mean {np.abs(err_t0).mean()*100:.2f} paise)"))
tb = {r.tenor: r.rate_pct for r in tbills.itertuples()}
fbz = dict(zip(fb_z.tenor, fb_z.zero_semi))
checks.append(("FBIL ZCYC equals the T-bill rate at 0.25 / 0.5 / 1.0 years",
               f"3M {tb['3 Months']:.2f} vs {fbz[0.25]:.2f}; 6M {tb['6 Months']:.2f} vs {fbz[0.5]:.2f}; "
               f"12M {tb['12 Months']:.2f} vs {fbz[1.0]:.2f}"))

class _Pub:
    def __init__(self, z): self._f = sp.published_curve(z, "cubic")
    def df(self, t): t = np.asarray(t, float); return cv.df_semiannual(self._f(t), t)
    def zero(self, t): return self._f(t)

G = sp.published_curve(fb_z, "cubic")
d_par = (cu.par_yield(_Pub(fb_z), grid) - fb_par["par_semi"].to_numpy()) * 100
checks.append(("Par formula (pro-rated stub coupon) applied to FBIL's ZCYC reproduces FBIL's par sheet",
               f"mean |diff| {np.abs(d_par).mean():.2f} bp, max {np.abs(d_par).max():.2f} bp over 200 tenors"))
sdl_fz = dict(zip(sdl_z.tenor, sdl_z.zero_semi))
checks.append(("SDL ZCYC front end = T-bill + spread (SDL methodology 5.2)",
               f"6M spread {sdl_fz[0.5]-tb['6 Months']:.2f} (also on 3M: {tb['3 Months']:.2f}+spread={sdl_fz[0.25]:.2f}); "
               f"12M spread {sdl_fz[1.0]-tb['12 Months']:.2f}"))
strips_fbil["t"] = [cv.yearfrac(m) for m in strips_fbil["maturity"]]
t_s = strips_fbil["t"].to_numpy()
strips_fbil["px_model"] = 100.0 * cv.df_semiannual(G(t_s), t_s)
strips_fbil["px_err"] = strips_fbil["px_model"] - strips_fbil["price"]
m6 = strips_fbil["t"] >= 0.5
S["strips_val"] = {"n": int(m6.sum()), "mae_paise": float(strips_fbil.loc[m6, "px_err"].abs().mean() * 100),
                   "max_paise": float(strips_fbil.loc[m6, "px_err"].abs().max() * 100)}
checks.append(("FBIL STRIP prices = 100 x DF from FBIL's ZCYC (act/365.25 from 15-Sep)",
               f"{S['strips_val']['n']} STRIPS of 6M+: mean |error| {S['strips_val']['mae_paise']:.2f} paise, "
               f"max {S['strips_val']['max_paise']:.2f} paise"))
save(pd.DataFrame(checks, columns=["check", "result"]), "convention_checks.csv")
save(strips_fbil.loc[:, ["isin", "name", "maturity", "t", "price", "px_model", "px_err"]].round(5), "fbil_strips_validation.csv")
S["price_check"] = {"mean_paise": float(np.abs(err).mean() * 100), "max_paise": float(np.abs(err).max() * 100)}
S["par_formula_check"] = {"mean_bp": float(np.abs(d_par).mean()), "max_bp": float(np.abs(d_par).max())}

# ------------------------------------------------------------------ 3. exact-fit bootstrap and variants
base, base_info = cu.bootstrap(inputs, tbills, "zero", use_3m=True)
S["exact"] = {"converged": base_info["converged"], "max_price_error": base_info["max_abs_price_error"],
              "d2_jump": base.max_second_derivative_jump(), "n_knots": base_info["n_knots"]}
own_sel = cu.select_inputs_rule(fixed)
variants = {
    "V1 Exact fit: spline on zero rate, natural ends": (base, base_info),
    "V2 As V1 without the 3M T-bill": cu.bootstrap(inputs, tbills, "zero", use_3m=False),
    "V3 Spline on -ln(discount factor)": cu.bootstrap(inputs, tbills, "logdf", use_3m=True),
    "V4 Not-a-knot end condition": cu.bootstrap(inputs, tbills, "zero", use_3m=True, bc="not-a-knot"),
    "V5 Own rule-based input selection": cu.bootstrap(own_sel, tbills, "zero", use_3m=True),
    "V6 Spline on instantaneous forward rate": cu.bootstrap_forward(inputs, tbills, use_3m=True),
}
rows, vdiff = [], {}
lo14 = grid <= 14
for name, (c, info) in variants.items():
    dd = (c.zero(grid) - fb_zero) * 100.0
    vdiff[name] = dd
    rows.append({"variant": name, "n_input_bonds": info["n_bonds"], "MAE_le14y_bp": np.abs(dd[lo14]).mean(),
                 "MAE_gt14y_bp": np.abs(dd[~lo14]).mean(), "MAE_all_bp": np.abs(dd).mean(),
                 "max_abs_bp": np.abs(dd).max(), "max_abs_at_tenor": grid[np.abs(dd).argmax()]})
vtab = pd.DataFrame(rows)
save(vtab.round(4), "variant_comparison.csv")
S["variants"] = vtab.round(3).to_dict(orient="records")

# ------------------------------------------------------------------ 4. submitted smoothed curve
smooth, sm_info = en.ls_fit(inputs, tbills, SETTLE, lam=P["lam"], lam_slope=P["slope"])
my_ex, my_sm = base.zero(grid), smooth.zero(grid)
par_ex, par_sm = cu.par_yield(base, grid), en.par_yield(smooth, grid)
cmp_tab = pd.DataFrame({
    "tenor_years": grid, "fbil_zero_semi": fb_zero,
    "exact_zero_semi": my_ex, "exact_diff_bp": (my_ex - fb_zero) * 100,
    "smooth_zero_semi": my_sm, "smooth_diff_bp": (my_sm - fb_zero) * 100,
    "fbil_par_semi": fb_par["par_semi"], "exact_par_semi": par_ex, "smooth_par_semi": par_sm,
    "exact_par_diff_bp": (par_ex - fb_par["par_semi"].to_numpy()) * 100,
    "smooth_par_diff_bp": (par_sm - fb_par["par_semi"].to_numpy()) * 100})
save(cmp_tab.round(5), "zcyc_exact_and_smoothed_vs_fbil.csv")

segs = [(0, 1), (1, 3), (3, 5), (5, 10), (10, 14), (14, 20), (20, 30), (30, 40), (40, 50)]
seg_rows = []
for a, b in segs:
    m = (grid > a) & (grid <= b)
    seg_rows.append({"segment_years": f"{a}-{b}", "n_tenors": int(m.sum()),
                     "exact_MAE_bp": cmp_tab.loc[m, "exact_diff_bp"].abs().mean(),
                     "smooth_MAE_bp": cmp_tab.loc[m, "smooth_diff_bp"].abs().mean(),
                     "smooth_mean_bp": cmp_tab.loc[m, "smooth_diff_bp"].mean(),
                     "smooth_max_abs_bp": cmp_tab.loc[m, "smooth_diff_bp"].abs().max(),
                     "exact_par_MAE_bp": cmp_tab.loc[m, "exact_par_diff_bp"].abs().mean(),
                     "smooth_par_MAE_bp": cmp_tab.loc[m, "smooth_par_diff_bp"].abs().mean()})
seg_tab = pd.DataFrame(seg_rows)
save(seg_tab.round(3), "segment_errors.csv")
S["segments"] = seg_tab.round(2).to_dict(orient="records")

def summ(col):
    dd = cmp_tab[col]
    return {"mae": float(dd.abs().mean()), "mae_le10": float(dd[grid <= 10].abs().mean()),
            "mae_le14": float(dd[lo14].abs().mean()), "mae_gt14": float(dd[~lo14].abs().mean()),
            "max": float(dd.abs().max()), "max_at": float(grid[dd.abs().argmax()]),
            "within_2bp_pct": float((dd.abs() <= 2).mean() * 100)}
S["exact_vs_fbil"], S["smooth_vs_fbil"] = summ("exact_diff_bp"), summ("smooth_diff_bp")
S["smooth_price_err_paise"] = float(sm_info["mean_abs_price_err"] * 100)
S["smooth_d2_jump"] = smooth.d2_jump()

# ------------------------------------------------------------------ 5. input bonds
ib = inputs.sort_values("maturity").copy()
ib["t_years"] = [cv.yearfrac(m) for m in ib["maturity"]]
ib["accrued"] = [cv.accrued_interest(r.coupon, r.maturity) for r in ib.itertuples()]
ib["dirty_price"] = ib["price"] + ib["accrued"]
ib["exact_zero_at_maturity"] = base.zero(ib["t_years"].to_numpy())
ib["fbil_zero_at_maturity"] = G(ib["t_years"].to_numpy())
fp = []
for r in ib.itertuples():
    cfs = cv.cash_flows(r.coupon, r.maturity)
    tj = np.array([cv.yearfrac(x) for x, _ in cfs]); a = np.array([v for _, v in cfs])
    fp.append(float(np.dot(a, cv.df_semiannual(G(tj), tj))) - r.dirty_price)
ib["fbil_curve_repricing_error"] = fp
save(ib[["isin", "coupon", "maturity", "t_years", "price", "accrued", "dirty_price", "ytm", "input_status",
         "exact_zero_at_maturity", "fbil_zero_at_maturity", "fbil_curve_repricing_error"]].round(5), "input_bonds.csv")
gap_at_inputs = (ib["exact_zero_at_maturity"] - ib["fbil_zero_at_maturity"]) * 100
long_ = ib["t_years"] > 14
S["exact_gap_at_input_maturities_gt14_bp"] = float(gap_at_inputs[long_].abs().mean())
fpa = np.abs(np.array(fp)) * 100
S["fbil_repricing"] = {"mean_paise": float(fpa.mean()), "gt14_paise": float(fpa[long_.to_numpy()].mean()),
                       "traded_paise": float(fpa[(ib.input_status == "T").to_numpy()].mean()),
                       "proxy_paise": float(fpa[(ib.input_status == "Proxy").to_numpy()].mean())}
_t = ib["t_years"].to_numpy(); _g = np.diff(_t)
S["gaps_beyond_14"] = [round(float(g), 1) for g, t in zip(_g, _t[1:]) if t > 14.0 and g > 3.0]
S["n_inputs_le14"], S["n_inputs_gt14"] = int((_t <= 14).sum()), int((_t > 14).sum())
S["first_input_years"], S["last_input_years"] = float(_t[0]), float(_t[-1])
wide = int(np.argmax(np.where(_t[1:] > 14, _g, 0)))
S["widest_gap"] = [float(_t[wide]), float(_t[wide + 1])]
save(own_sel[["isin", "coupon", "maturity", "price", "ytm", "is_input"]], "own_input_selection.csv")

# ------------------------------------------------------------------ 6. charts
tg = np.linspace(0.02, 50, 1500)
# 02: long end, where the two fitting methods differ
fig, ax = plt.subplots(figsize=(10, 4.8))
m = grid >= 14
ax.plot(grid[m], fb_zero[m], color=NAVY, lw=2.4, label="FBIL published ZCYC")
ax.plot(tg[tg >= 14], smooth.zero(tg[tg >= 14]), color=ORANGE, lw=1.8, ls="--", label="Smoothed fit (submitted)")
ax.plot(tg[tg >= 14], base.zero(tg[tg >= 14]), color=GREY, lw=1.3, ls=":", label="Exact-fit bootstrap")
for t in _t[_t >= 14]:
    ax.axvline(t, color=TEAL, lw=0.9, alpha=0.6)
for t0, t1 in zip(_t[:-1], _t[1:]):
    if t0 >= 14 and t1 - t0 > 5:
        ax.axvspan(t0, t1, color=RED, alpha=0.07)
        ax.text((t0 + t1) / 2, 7.45, "%.1f-year gap" % (t1 - t0), ha="center", color=RED, fontsize=9)
ax.set_xlabel("Tenor (years)"); ax.set_ylabel("Semi-annual zero rate (%)")
ax.set_title("Beyond 14 years, 11 Sep 2026 (teal lines: input bond maturities; shaded: gaps over 5 years)", loc="left", fontsize=11)
ax.legend(frameon=False, loc="upper left")
plt.tight_layout(); plt.savefig(os.path.join(CH, "02_long_end_zoom.png")); plt.close()

# 03: variants
fig, ax = plt.subplots(figsize=(10, 4.8))
for (name, dd), col in zip(list(vdiff.items())[:5], [ORANGE, TEAL, NAVY, GREY, RED]):
    ax.plot(grid, dd, lw=2.2 if name.startswith("V1") else 1.1, color=col, label=name.split(" ", 1)[0] + " " + name.split(" ", 1)[1][:40],
            zorder=6 if name.startswith("V1") else 2)
ax.axhline(0, color="k", lw=0.6); ax.set_ylim(-30, 30)
ax.set_xlabel("Tenor (years)"); ax.set_ylabel("Variant minus FBIL zero rate (bp)")
ax.set_title("Exact-fit variants, 11 Sep 2026 (V6 is off the scale, see table)", loc="left", fontsize=11)
ax.legend(frameon=False, fontsize=8.5, loc="upper left")
plt.tight_layout(); plt.savefig(os.path.join(CH, "03_variants.png")); plt.close()

# 04: par curve of the submitted curve
fig, ax = plt.subplots(2, 1, figsize=(10, 6.2), gridspec_kw={"height_ratios": [2, 1]}, sharex=True)
ax[0].plot(grid, fb_par["par_semi"], color=NAVY, lw=2.4, label="FBIL par yield")
ax[0].plot(grid, par_sm, color=ORANGE, lw=1.7, ls="--", label="Par yield from our smoothed ZCYC")
ax[0].set_ylabel("Par yield, semi-annual (%)"); ax[0].legend(frameon=False, loc="lower right")
ax[0].set_title("Par yield curve, 11 Sep 2026", loc="left", fontsize=11)
ax[1].axhspan(-0.5, 0.5, color=GREY, alpha=0.15)
ax[1].plot(grid, cmp_tab["smooth_par_diff_bp"], color=ORANGE); ax[1].axhline(0, color=GREY, lw=0.8)
ax[1].set_ylabel("Ours minus FBIL (bp)"); ax[1].set_xlabel("Tenor (years)")
plt.tight_layout(); plt.savefig(os.path.join(CH, "04_par_curve.png")); plt.close()

# 12: error by maturity segment, both methods
fig, ax = plt.subplots(figsize=(10, 4.6))
x = np.arange(len(seg_tab)); w = 0.38
ax.bar(x - w / 2, seg_tab.exact_MAE_bp, w, color=GREY, label="Exact-fit bootstrap")
ax.bar(x + w / 2, seg_tab.smooth_MAE_bp, w, color=ORANGE, label="Smoothed fit (submitted)")
for i, (a, b) in enumerate(zip(seg_tab.exact_MAE_bp, seg_tab.smooth_MAE_bp)):
    ax.text(i - w / 2, a + 0.2, f"{a:.1f}", ha="center", fontsize=8.5)
    ax.text(i + w / 2, b + 0.2, f"{b:.1f}", ha="center", fontsize=8.5)
ax.set_xticks(x); ax.set_xticklabels([s.replace("-", "–") for s in seg_tab.segment_years])
ax.set_xlabel("Maturity segment (years)"); ax.set_ylabel("Mean absolute gap to FBIL (bp)")
ax.set_title("Gap to FBIL's ZCYC by maturity segment, 11 Sep 2026", loc="left", fontsize=11)
ax.legend(frameon=False)
plt.tight_layout(); plt.savefig(os.path.join(CH, "12_segments.png")); plt.close()

for old in ["01_zcyc_comparison.png", "legacy_05_strips_fbilcurve.png", "06_strips_validation.png"]:
    if os.path.exists(os.path.join(CH, old)):
        os.remove(os.path.join(CH, old))

json.dump(S, open(os.path.join(OUT, "results_summary.json"), "w"), indent=2, default=float)
print(json.dumps({k: S[k] for k in ["settlement", "exact_vs_fbil", "smooth_vs_fbil", "fbil_repricing",
                                    "exact_gap_at_input_maturities_gt14_bp", "strips_val"]}, indent=1, default=float))
print(vtab.round(2).to_string(index=False))
print(seg_tab.round(2).to_string(index=False))
