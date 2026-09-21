"""Reproduces every calibration and robustness number quoted in the README and deck.

    python tune_and_checks.py      (run this FIRST: it writes outputs/tuned_params.json)

1. Smoothing parameters. A grid of (lambda, slope) is scored against FBIL's published ZCYC on the
   four August dates only. The August minimum is written to tuned_params.json and used unchanged by
   run_multidate.py and run_strips.py. 11 September is scored but never used for the choice.
   NOTE: this is a calibration to FBIL's curve. Two numbers are chosen this way; nothing else is.
2. Rounding control. How much of FBIL's input mispricing could come from publishing zero rates to
   two decimals on a 0.25-year grid?
3. Day-count basis for STRIPS (act/365.25, act/365, act/360, 30/360), all five dates.
4. T-bill rates used directly vs converted to bond-equivalent yields.
5. Leave-one-out hold-out: refit without each interior input bond and price it from the others.
   This is the only accuracy test that does not use FBIL's curve at all.
"""
import itertools
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
warnings.filterwarnings("ignore")
import multidate as md   # noqa: E402
import engine as en      # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "additional_material", "outputs")
TAB, CH = os.path.join(OUT, "tables"), os.path.join(OUT, "charts")
os.makedirs(TAB, exist_ok=True); os.makedirs(CH, exist_ok=True)
TUNE = ["2026-08-05", "2026-08-14", "2026-08-21", "2026-08-28"]
TEST = "2026-09-11"
LAMS = [0.002, 0.005, 0.01, 0.02, 0.05, 0.1]
SLOPES = [0.0, 0.1, 0.2, 0.3, 0.5, 1.0]

D = {}
for iso in md.DATES:
    s, _ = md.detect_settlement(iso)
    g = md.load_gsec(iso)
    D[iso] = dict(settle=s, inp=g[g["is_input"] & ~g["is_frb"]], tb=md.load_tbills(iso),
                  z=md.load_zcyc(iso), strips=md.load_strips(iso))
R = {}

# ------------------------------------------------------------------ 1. smoothing parameters
rows = []
for lam, slope in itertools.product(LAMS, SLOPES):
    r = {"lam": lam, "slope": slope}
    for iso, d in D.items():
        c, _ = en.ls_fit(d["inp"], d["tb"], d["settle"], lam=lam, lam_slope=slope)
        r[iso] = en.score(c, d["z"])["mae"]
    r["august_mean"] = float(np.mean([r[i] for i in TUNE]))
    rows.append(r)
grid = pd.DataFrame(rows)
grid.round(3).to_csv(os.path.join(TAB, "tuning_grid.csv"), index=False)
best = grid.loc[grid["august_mean"].idxmin()]
LAM, SLOPE = float(best["lam"]), float(best["slope"])
near = grid[grid["august_mean"] <= best["august_mean"] + 0.25]
R["tuning"] = {"lam": LAM, "slope": SLOPE, "august_mean_bp": float(best["august_mean"]),
               "test_bp_at_choice": float(best[TEST]),
               "test_bp_best_in_grid": float(grid[TEST].min()),
               "n_grid": len(grid), "n_within_0.25bp_of_best": int(len(near)),
               "august_range_near_best": [float(near["august_mean"].min()), float(near["august_mean"].max())],
               "test_range_near_best": [float(near[TEST].min()), float(near[TEST].max())]}
json.dump({"lam": LAM, "slope": SLOPE, "tuned_on": TUNE, "held_out": TEST},
          open(os.path.join(OUT, "tuned_params.json"), "w"), indent=2)

# ------------------------------------------------------------------ 2. rounding control (11 Sep)
d = D[TEST]
c_ex, _ = en.bootstrap(d["inp"], d["tb"], d["settle"], use_3m=True)
flows, tgt = en.bond_flows(d["inp"], d["settle"])
g_ = d["z"]["tenor"].to_numpy(float)
rounded = np.round(c_ex.zero(g_), 2)
Fr = CubicSpline(g_, rounded, bc_type="natural")
Ff = CubicSpline(g_, d["z"]["zero_semi"].to_numpy(float), bc_type="natural")
rep = lambda F: np.array([np.dot(cf, en.df_semi(F(tj), tj)) for tj, cf in flows]) - tgt
R["rounding_control"] = {
    "exact_fit_paise": float(np.abs(rep(c_ex.zero)).mean() * 100),
    "exact_fit_rounded_to_fbil_grid_paise": float(np.abs(rep(Fr)).mean() * 100),
    "fbil_published_paise": float(np.abs(rep(Ff)).mean() * 100)}

# ------------------------------------------------------------------ 3. day-count basis for STRIPS
def yf(d0, d1, basis):
    n = (d1 - d0).days
    if basis == "30/360":
        return (360 * (d1.year - d0.year) + 30 * (d1.month - d0.month) + min(d1.day, 30) - min(d0.day, 30)) / 360.0
    return n / {"act/365.25": 365.25, "act/365": 365.0, "act/360": 360.0}[basis]

dc = []
for iso, d in D.items():
    F = CubicSpline(d["z"]["tenor"], d["z"]["zero_semi"], bc_type="natural")
    row = {"date": iso}
    for b in ["act/365.25", "act/365", "act/360", "30/360"]:
        t = np.array([yf(d["settle"], m, b) for m in d["strips"]["maturity"]]); k = t >= 0.5
        px = 100 * en.df_semi(F(t[k]), t[k])
        row[b] = float(np.abs(px - d["strips"]["price"].to_numpy()[k]).mean() * 100)
    dc.append(row)
dc = pd.DataFrame(dc)
dc.round(3).to_csv(os.path.join(TAB, "daycount_check.csv"), index=False)
R["daycount_mean_paise"] = {b: float(dc[b].mean()) for b in ["act/365.25", "act/365", "act/360", "30/360"]}

# ------------------------------------------------------------------ 4. T-bill rates: direct vs bond-equivalent
bey = []
for iso, d in D.items():
    a = en.score(en.bootstrap(d["inp"], d["tb"], d["settle"], use_3m=True)[0], d["z"])
    b = en.score(en.bootstrap(d["inp"], d["tb"], d["settle"], use_3m=True, bey=True)[0], d["z"])
    bey.append({"date": iso, "direct_le14": a["mae_le14"], "bey_le14": b["mae_le14"]})
bey = pd.DataFrame(bey)
bey.round(3).to_csv(os.path.join(TAB, "tbill_direct_vs_bey.csv"), index=False)
R["tbill_le14_bp"] = {"direct": float(bey.direct_le14.mean()), "bond_equivalent": float(bey.bey_le14.mean())}

# ------------------------------------------------------------------ 5. leave-one-out hold-out
def ytm_of(bond, curve, settle):
    cfs = md.cash_flows(bond.coupon, bond.maturity, settle)
    tj = np.array([md.yearfrac(x, settle) for x, _ in cfs]); a = np.array([v for _, v in cfs])
    dirty = float(np.dot(a, curve.df(tj)))
    return brentq(lambda y: md.dirty_from_ytm(bond.coupon, bond.maturity, y, settle) - dirty, 0.1, 30.0)

loo = []
for iso, d in D.items():
    inp = d["inp"].sort_values("maturity").reset_index(drop=True)
    for i in range(1, len(inp) - 1):                      # interior bonds only: no extrapolation
        rest, b = inp.drop(index=i), inp.iloc[i]
        ce, _ = en.bootstrap(rest, d["tb"], d["settle"], use_3m=True)
        cs, _ = en.ls_fit(rest, d["tb"], d["settle"], lam=LAM, lam_slope=SLOPE)
        loo.append({"date": iso, "maturity": b.maturity, "t_years": md.yearfrac(b.maturity, d["settle"]),
                    "status": b.input_status, "ytm": b.ytm,
                    "exact_err_bp": (ytm_of(b, ce, d["settle"]) - b.ytm) * 100,
                    "smooth_err_bp": (ytm_of(b, cs, d["settle"]) - b.ytm) * 100})
loo = pd.DataFrame(loo)
loo.round(4).to_csv(os.path.join(TAB, "loo_holdout.csv"), index=False)
lo = loo.t_years <= 14
R["loo"] = {"n": len(loo),
            "exact_mae_bp": float(loo.exact_err_bp.abs().mean()), "smooth_mae_bp": float(loo.smooth_err_bp.abs().mean()),
            "exact_le14": float(loo.exact_err_bp[lo].abs().mean()), "smooth_le14": float(loo.smooth_err_bp[lo].abs().mean()),
            "exact_gt14": float(loo.exact_err_bp[~lo].abs().mean()), "smooth_gt14": float(loo.smooth_err_bp[~lo].abs().mean()),
            "exact_median": float(loo.exact_err_bp.abs().median()), "smooth_median": float(loo.smooth_err_bp.abs().median())}
json.dump(R, open(os.path.join(OUT, "checks_summary.json"), "w"), indent=2, default=float)

# chart: hold-out errors by maturity, all five dates pooled
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "savefig.dpi": 190})
fig, ax = plt.subplots(figsize=(10, 4.8))
ax.axhline(0, color="#8A8F98", lw=0.8)
ax.scatter(loo.t_years, loo.exact_err_bp, s=26, color="#8A8F98", label="Exact-fit bootstrap")
ax.scatter(loo.t_years, loo.smooth_err_bp, s=26, color="#E07B39", label="Smoothed fit")
ax.axvline(14, color="#1F3A5F", lw=1, ls="--"); ax.text(14.3, ax.get_ylim()[1] * 0.9, "14 years", color="#1F3A5F", fontsize=9)
ax.set_xlabel("Residual maturity of the bond left out (years)")
ax.set_ylabel("Model YTM minus published YTM (bp)")
ax.set_title("Leave-one-out test: each input bond priced from a curve fitted without it (5 dates)", loc="left", fontsize=11)
ax.legend(frameon=False)
plt.tight_layout(); plt.savefig(os.path.join(CH, "11_holdout.png")); plt.close()

print(json.dumps(R, indent=1, default=float))
print(grid.sort_values("august_mean").head(8).round(2).to_string(index=False))
