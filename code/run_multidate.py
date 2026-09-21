"""Multi-date study: builds both curves on all five dates, scores them against FBIL,
and writes tables + charts.   Run:  python run_multidate.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.interpolate import CubicSpline

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
import multidate as md      # noqa: E402
import engine as en         # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "additional_material", "outputs")
TAB, CH = os.path.join(OUT, "tables"), os.path.join(OUT, "charts")
os.makedirs(TAB, exist_ok=True); os.makedirs(CH, exist_ok=True)

_P = json.load(open(os.path.join(OUT, "tuned_params.json")))   # written by tune_and_checks.py
LAM, SLOPE = _P["lam"], _P["slope"]   # chosen on the four August dates only; 11-Sep is held out
TUNE = ["2026-08-05", "2026-08-14", "2026-08-21", "2026-08-28"]
TEST = "2026-09-11"

NAVY, ORANGE, TEAL, GREY, RED = "#1F3A5F", "#E07B39", "#2A9D8F", "#8A8F98", "#C0392B"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "figure.dpi": 100, "savefig.dpi": 190, "font.size": 11})

def shape_checks(c):
    """No-arbitrage sanity checks on a 0.25-year grid out to 50 years."""
    t = np.arange(0.25, 50.001, 0.25)
    d = c.df(t)
    fwd = (d[:-1] / d[1:] - 1.0) * 4.0 * 100.0          # simple 3-month forward rates, %
    z = c.zero(t)
    return dict(df_decreasing=bool(np.all(np.diff(d) < 0)), min_fwd_3m=float(fwd.min()),
                max_fwd_3m=float(fwd.max()), zero_min=float(z.min()), zero_max=float(z.max()))


rows, curves, S = [], {}, {}
for iso in md.DATES:
    settle, _ = md.detect_settlement(iso)
    g, tb, z, par = md.load_gsec(iso), md.load_tbills(iso), md.load_zcyc(iso), md.load_par(iso)
    inp = g[g["is_input"] & ~g["is_frb"]]
    c_ex, i_ex = en.bootstrap(inp, tb, settle, use_3m=True)
    c_sm, i_sm = en.ls_fit(inp, tb, settle, lam=LAM, lam_slope=SLOPE)
    q_ex, q_sm = en.score(c_ex, z), en.score(c_sm, z)

    F = CubicSpline(z["tenor"], z["zero_semi"], bc_type="natural")
    flows, tgt = en.bond_flows(inp, settle)
    fb_px = float(np.abs(np.array([np.dot(cf, en.df_semi(F(tj), tj)) for tj, cf in flows]) - tgt).mean() * 100)

    grid = z["tenor"].to_numpy(float)
    pe = en.par_yield(c_ex, grid); ps = en.par_yield(c_sm, grid)
    par_ex = float(np.abs(pe - par["par_semi"].to_numpy()).mean() * 100)
    par_sm = float(np.abs(ps - par["par_semi"].to_numpy()).mean() * 100)

    rows.append(dict(date=iso, settle=str(settle), n_inputs=len(inp),
                     exact_mae=q_ex["mae"], exact_le14=q_ex["mae_le14"], exact_gt14=q_ex["mae_gt14"], exact_max=q_ex["max"],
                     smooth_mae=q_sm["mae"], smooth_le14=q_sm["mae_le14"], smooth_gt14=q_sm["mae_gt14"], smooth_max=q_sm["max"],
                     exact_par_mae=par_ex, smooth_par_mae=par_sm,
                     smooth_price_err_paise=i_sm["mean_abs_price_err"] * 100, fbil_price_err_paise=fb_px,
                     smooth_d2_jump=c_sm.d2_jump(), exact_d2_jump=c_ex.d2_jump(),
                     **shape_checks(c_sm)))
    curves[iso] = dict(grid=grid, fbil=z["zero_semi"].to_numpy(float),
                       exact=c_ex.zero(grid), smooth=c_sm.zero(grid),
                       bond_t=i_ex["bond_t"], ytm=inp.sort_values("maturity")["ytm"].to_numpy(float))

df = pd.DataFrame(rows)
df.round(4).to_csv(os.path.join(TAB, "multidate_results.csv"), index=False)

S["lam"], S["slope"] = LAM, SLOPE
S["tune_dates"], S["test_date"] = TUNE, TEST
for k in ["exact_mae", "exact_le14", "exact_gt14", "exact_max", "smooth_mae", "smooth_le14",
          "smooth_gt14", "smooth_max", "exact_par_mae", "smooth_par_mae",
          "smooth_price_err_paise", "fbil_price_err_paise"]:
    S["mean_" + k] = float(df[k].mean())
t = df[df.date == TEST].iloc[0]
S["oos"] = {k: float(t[k]) for k in ["exact_mae", "exact_le14", "exact_gt14", "exact_max",
                                     "smooth_mae", "smooth_le14", "smooth_gt14", "smooth_max"]}
S["improvement_pct"] = float(100 * (1 - df.smooth_mae.mean() / df.exact_mae.mean()))
S["improvement_gt14_pct"] = float(100 * (1 - df.smooth_gt14.mean() / df.exact_gt14.mean()))
S["max_d2_jump"] = float(df.smooth_d2_jump.max())
S["per_date"] = df.round(4).to_dict(orient="records")
S["shape"] = {"df_decreasing_all_dates": bool(df.df_decreasing.all()), "min_fwd_3m": float(df.min_fwd_3m.min()),
              "max_fwd_3m": float(df.max_fwd_3m.max()), "zero_min": float(df.zero_min.min()), "zero_max": float(df.zero_max.max())}

# ---------------------------------------------------------------- the delivered curves (task 2 output)
iso = TEST
settle, _ = md.detect_settlement(iso)
g_, tb_, z_, par_ = md.load_gsec(iso), md.load_tbills(iso), md.load_zcyc(iso), md.load_par(iso)
inp_ = g_[g_["is_input"] & ~g_["is_frb"]]
c_fin, _ = en.ls_fit(inp_, tb_, settle, lam=LAM, lam_slope=SLOPE)
grid_ = z_["tenor"].to_numpy(float)
zero_sa = c_fin.zero(grid_)
zero_an = en.semi_to_annual(zero_sa)
par_sa = en.par_yield(c_fin, grid_)
final = pd.DataFrame({"tenor_years": grid_, "zero_semi_annual_pct": zero_sa, "zero_annualised_pct": zero_an,
                      "par_semi_annual_pct": par_sa, "discount_factor": c_fin.df(grid_),
                      "fbil_zero_semi_annual_pct": z_["zero_semi"].to_numpy(float),
                      "fbil_par_semi_annual_pct": par_["par_semi"].to_numpy(float)})
final["zero_diff_bp"] = (final.zero_semi_annual_pct - final.fbil_zero_semi_annual_pct) * 100
final["par_diff_bp"] = (final.par_semi_annual_pct - final.fbil_par_semi_annual_pct) * 100
final.round(6).to_csv(os.path.join(TAB, "final_curve_2026-09-11.csv"), index=False)

S["curve_points"] = {str(t): {"zero_sa": float(final.loc[final.tenor_years == t, "zero_semi_annual_pct"].iloc[0]),
                              "zero_an": float(final.loc[final.tenor_years == t, "zero_annualised_pct"].iloc[0]),
                              "par_sa": float(final.loc[final.tenor_years == t, "par_semi_annual_pct"].iloc[0])}
                     for t in [0.25, 1, 2, 5, 10, 14, 20, 30, 40, 50]}
S["curve_date"] = iso

# ---------------------------------------------------------------- one identical chart set per method (11 Sep)
# Parts A and B of the deck show the exact fit and the smoothed fit with the same five charts and the
# same axis limits, so each chart can be compared with its counterpart directly.
c_ex_fin, _ = en.bootstrap(inp_, tb_, settle, use_3m=True)
METHODS = {"exact": (c_ex_fin, "Exact-fit bootstrap", GREY), "smooth": (c_fin, "Smoothed fit", ORANGE)}
fb0, fbpar = z_["zero_semi"].to_numpy(float), par_["par_semi"].to_numpy(float)
inp_s = inp_.sort_values("maturity")
bt_ = np.array([md.yearfrac(m, settle) for m in inp_s["maturity"]])
tk = en.tbill_knots(tb_, use_3m=True)
SEGS = [(0, 1), (1, 3), (3, 5), (5, 10), (10, 14), (14, 20), (20, 30), (30, 40), (40, 50)]
gaps = {k: (c.zero(grid_) - fb0) * 100 for k, (c, _, _) in METHODS.items()}
pgaps = {k: (en.par_yield(c, grid_) - fbpar) * 100 for k, (c, _, _) in METHODS.items()}
GAP_LIM = (min(g.min() for g in gaps.values()) - 2, max(g.max() for g in gaps.values()) + 2)
PAR_LIM = (min(g.min() for g in pgaps.values()) - 1, max(g.max() for g in pgaps.values()) + 1)
SEG_MAX = max(max(np.abs(g[(grid_ > a) & (grid_ <= b)]).mean() for a, b in SEGS) for g in gaps.values()) * 1.15
DATE_MAX = max(df[[c for c in df.columns if c.startswith(("exact_", "smooth_")) and c.endswith(("mae", "le14", "gt14"))]].max()) * 1.15
tg = np.linspace(0.02, 50, 1500)

S["methods"] = {}
for key, (c, label, col) in METHODS.items():
    z_sa = c.zero(grid_); p_sa = en.par_yield(c, grid_); gap, pgap = gaps[key], pgaps[key]
    seg = [float(np.abs(gap[(grid_ > a) & (grid_ <= b)]).mean()) for a, b in SEGS]
    S["methods"][key] = {
        "mae": float(np.abs(gap).mean()), "mae_le14": float(np.abs(gap[grid_ <= 14]).mean()),
        "mae_gt14": float(np.abs(gap[grid_ > 14]).mean()), "max": float(np.abs(gap).max()),
        "max_at": float(grid_[np.abs(gap).argmax()]), "max_le14": float(np.abs(gap[grid_ <= 14]).max()),
        "max_gt14": float(np.abs(gap[grid_ > 14]).max()), "within_2bp_pct": float((np.abs(gap) <= 2).mean() * 100),
        "par_mae": float(np.abs(pgap).mean()), "par_max": float(np.abs(pgap).max()),
        "par_max_at": float(grid_[np.abs(pgap).argmax()]), "par_mae_gt20": float(np.abs(pgap[grid_ > 20]).mean()),
        "segments": {f"{a}-{b}": v for (a, b), v in zip(SEGS, seg)},
        "curve_points": {str(t): {"zero_sa": float(c.zero(t)), "zero_an": float(en.semi_to_annual(c.zero(t))),
                                  "par_sa": float(en.par_yield(c, [t])[0])} for t in [0.25, 1, 2, 5, 10, 14, 20, 30, 40, 50]},
        "peak": [float(tg[np.argmax(c.zero(tg))]), float(np.max(c.zero(tg)))]}

    # 1. output curves
    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.plot(grid_, z_sa, color=NAVY, lw=2.6, label="Zero coupon yield curve (semi-annual)")
    ax.plot(grid_, en.semi_to_annual(z_sa), color=TEAL, lw=1.6, ls="-.", label="Zero coupon yield curve (annualised)")
    ax.plot(grid_, p_sa, color=ORANGE, lw=2.0, ls="--", label="Par yield curve (semi-annual)")
    ax.scatter(bt_, inp_s["ytm"], s=22, color=GREY, zorder=5, label="Input bond YTMs")
    ax.scatter([q[0] for q in tk], [q[1] for q in tk], s=40, marker="s", color=RED, zorder=6, label="T-bill inputs (7D, 3M, 6M, 12M)")
    ax.set_xlabel("Residual maturity (years)"); ax.set_ylabel("Rate (% per annum)"); ax.set_xlim(-1, 51); ax.set_ylim(4.5, 8.9)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    ax.set_title(f"{label}: zero and par curves, 11 Sep 2026", loc="left", fontsize=11)
    plt.tight_layout(); plt.savefig(os.path.join(CH, f"{key}_1_curves.png")); plt.close()

    # 2. zero curve vs FBIL
    fig, ax = plt.subplots(2, 1, figsize=(10, 7.0), gridspec_kw={"height_ratios": [2.2, 1]}, sharex=True)
    ax[0].plot(grid_, fb0, color=NAVY, lw=2.4, label="FBIL published ZCYC")
    ax[0].plot(grid_, z_sa, color=col, lw=1.8, ls="--", label=label)
    ax[0].scatter(bt_, inp_s["ytm"], s=20, color=TEAL, zorder=5, label="Input bond YTMs")
    ax[0].set_ylabel("Semi-annual zero rate (%)"); ax[0].legend(frameon=False, loc="lower right", fontsize=9)
    ax[0].set_title(f"{label} vs FBIL's zero curve, 11 Sep 2026", loc="left", fontsize=11)
    ax[1].axhline(0, color=GREY, lw=0.8); ax[1].axhspan(-0.5, 0.5, color=GREY, alpha=0.2)
    ax[1].plot(grid_, gap, color=col, lw=1.8); ax[1].set_ylim(*GAP_LIM)
    ax[1].axvline(14, color=NAVY, lw=0.8, ls="--")
    ax[1].set_ylabel("Ours minus FBIL (bp)"); ax[1].set_xlabel("Tenor (years)")
    plt.tight_layout(); plt.savefig(os.path.join(CH, f"{key}_2_vs_fbil.png")); plt.close()

    # 3. par curve vs FBIL
    fig, ax = plt.subplots(2, 1, figsize=(10, 6.2), gridspec_kw={"height_ratios": [2, 1]}, sharex=True)
    ax[0].plot(grid_, fbpar, color=NAVY, lw=2.4, label="FBIL par yield")
    ax[0].plot(grid_, p_sa, color=col, lw=1.8, ls="--", label=f"Par yield from the {label.lower()}")
    ax[0].set_ylabel("Par yield, semi-annual (%)"); ax[0].legend(frameon=False, loc="lower right")
    ax[0].set_title(f"{label}: par yield vs FBIL, 11 Sep 2026", loc="left", fontsize=11)
    ax[1].axhspan(-0.5, 0.5, color=GREY, alpha=0.2); ax[1].axhline(0, color=GREY, lw=0.8)
    ax[1].plot(grid_, pgap, color=col); ax[1].set_ylim(*PAR_LIM)
    ax[1].set_ylabel("Ours minus FBIL (bp)"); ax[1].set_xlabel("Tenor (years)")
    plt.tight_layout(); plt.savefig(os.path.join(CH, f"{key}_3_par.png")); plt.close()

    # 4. gap by segment (11 Sep) and by date
    fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.6), gridspec_kw={"width_ratios": [1.25, 1]})
    xs = np.arange(len(SEGS))
    ax[0].bar(xs, seg, 0.6, color=col)
    for i, v in enumerate(seg):
        ax[0].text(i, v + SEG_MAX * 0.015, f"{v:.1f}", ha="center", fontsize=8.5)
    ax[0].axvline(4.5, color=NAVY, lw=0.8, ls="--")
    ax[0].set_xticks(xs); ax[0].set_xticklabels([f"{a}–{b}" for a, b in SEGS], fontsize=9)
    ax[0].set_ylim(0, SEG_MAX); ax[0].set_xlabel("Maturity segment (years)"); ax[0].set_ylabel("Mean absolute gap to FBIL (bp)")
    ax[0].set_title("By maturity segment, 11 Sep", loc="left", fontsize=11)
    xd = np.arange(len(df)); w = 0.27
    for j, (suf, name, alpha) in enumerate([("mae", "All tenors", 1.0), ("le14", "Up to 14y", 0.55), ("gt14", "Beyond 14y", 0.3)]):
        ax[1].bar(xd + (j - 1) * w, df[f"{key}_{suf}"], w, color=col, alpha=alpha, edgecolor=col, label=name)
    ax[1].axvspan(3.5, 4.5, color=TEAL, alpha=0.08)
    ax[1].set_xticks(xd); ax[1].set_xticklabels([d_[5:].replace("-", "/") for d_ in df.date])
    ax[1].set_ylim(0, DATE_MAX); ax[1].set_ylabel("Mean absolute gap to FBIL (bp)")
    ax[1].set_title("By date (shaded: 11 Sep)", loc="left", fontsize=11); ax[1].legend(frameon=False, fontsize=9, loc="upper left")
    plt.tight_layout(); plt.savefig(os.path.join(CH, f"{key}_4_accuracy.png")); plt.close()

    # 5. long end
    fig, ax = plt.subplots(figsize=(10, 4.8))
    m = grid_ >= 14
    ax.plot(grid_[m], fb0[m], color=NAVY, lw=2.4, label="FBIL published ZCYC")
    ax.plot(tg[tg >= 14], c.zero(tg[tg >= 14]), color=col, lw=1.9, ls="--", label=label)
    for t_ in bt_[bt_ >= 14]:
        ax.axvline(t_, color=TEAL, lw=0.9, alpha=0.6)
    for t0, t1 in zip(bt_[:-1], bt_[1:]):
        if t0 >= 14 and t1 - t0 > 5:
            ax.axvspan(t0, t1, color=RED, alpha=0.07)
            ax.text((t0 + t1) / 2, 7.3, "%.1f-year gap" % (t1 - t0), ha="center", color=RED, fontsize=9)
    ax.set_ylim(7.2, 8.7); ax.set_xlabel("Tenor (years)"); ax.set_ylabel("Semi-annual zero rate (%)")
    ax.set_title(f"{label} beyond 14 years (teal lines: input maturities; shaded: gaps over 5 years)", loc="left", fontsize=11)
    ax.legend(frameon=False, loc="upper left")
    plt.tight_layout(); plt.savefig(os.path.join(CH, f"{key}_5_long_end.png")); plt.close()

json.dump(S, open(os.path.join(OUT, "multidate_summary.json"), "w"), indent=2, default=float)

# ---------------------------------------------------------------- charts
fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.6))
x = np.arange(len(df)); w = 0.38
lbl = [d[5:].replace("-", "/") for d in df.date]
ax[0].bar(x - w/2, df.exact_mae, w, color=GREY, label="Exact-fit bootstrap")
ax[0].bar(x + w/2, df.smooth_mae, w, color=ORANGE, label="Smoothed fit (submitted)")
ax[0].set_xticks(x); ax[0].set_xticklabels(lbl); ax[0].set_ylabel("Mean absolute gap to FBIL ZCYC (bp)")
ax[0].set_title("All tenors", loc="left", fontsize=11)
for i, (a, b) in enumerate(zip(df.exact_mae, df.smooth_mae)):
    ax[0].text(i - w/2, a + .1, f"{a:.1f}", ha="center", fontsize=8)
    ax[0].text(i + w/2, b + .1, f"{b:.1f}", ha="center", fontsize=8, fontweight="bold")
ax[0].axvspan(3.5, 4.5, color=TEAL, alpha=0.10)
ax[0].text(4, ax[0].get_ylim()[1]*0.93, "held out", ha="center", fontsize=9, color=TEAL)
ax[1].bar(x - w/2, df.exact_gt14, w, color=GREY, label="Exact-fit")
ax[1].bar(x + w/2, df.smooth_gt14, w, color=ORANGE, label="Smoothed")
ax[1].set_xticks(x); ax[1].set_xticklabels(lbl); ax[1].set_ylabel("Mean absolute gap to FBIL ZCYC (bp)")
ax[1].set_title("Tenors beyond 14 years", loc="left", fontsize=11)
fig.legend(*ax[0].get_legend_handles_labels(), frameon=False, loc="lower center", ncol=2)
ax[0].set_ylim(0, df.exact_mae.max() * 1.18)
plt.tight_layout(rect=(0, 0.07, 1, 1)); plt.savefig(os.path.join(CH, "07_multidate_accuracy.png")); plt.close()

d = curves[TEST]
fig, ax = plt.subplots(2, 1, figsize=(10, 7.2), gridspec_kw={"height_ratios": [2.2, 1]}, sharex=True)
ax[0].plot(d["grid"], d["fbil"], color=NAVY, lw=2.4, label="FBIL published ZCYC (reference)")
ax[0].plot(d["grid"], d["smooth"], color=ORANGE, lw=1.7, ls="--", label="Smoothed fit (submitted)")
ax[0].plot(d["grid"], d["exact"], color=GREY, lw=1.2, ls=":", label="Exact-fit bootstrap")
ax[0].scatter(d["bond_t"], d["ytm"], s=20, color=TEAL, zorder=5, label="Input bond YTMs")
ax[0].set_ylabel("Semi-annual zero rate (%)"); ax[0].legend(frameon=False, loc="lower right", fontsize=9)
ax[0].set_title("Zero curves, 11 Sep 2026 (held-out date)", loc="left", fontsize=11)
ax[1].axhline(0, color=GREY, lw=0.8); ax[1].axhspan(-0.5, 0.5, color=GREY, alpha=0.15)
ax[1].plot(d["grid"], (d["exact"] - d["fbil"]) * 100, color=GREY, lw=1.2, ls=":", label="Exact-fit")
ax[1].plot(d["grid"], (d["smooth"] - d["fbil"]) * 100, color=ORANGE, lw=1.7, label="Smoothed")
ax[1].set_ylabel("Gap to FBIL (bp)"); ax[1].set_xlabel("Tenor (years)")
ax[1].legend(frameon=False, loc="lower left", fontsize=9)
plt.tight_layout(); plt.savefig(os.path.join(CH, "08_final_curve.png")); plt.close()

print(df.round(2).to_string(index=False))
print("\nMEAN  exact MAE %.2f (<=14y %.2f, >14y %.2f, max %.1f)" %
      (df.exact_mae.mean(), df.exact_le14.mean(), df.exact_gt14.mean(), df.exact_max.mean()))
print("MEAN smooth MAE %.2f (<=14y %.2f, >14y %.2f, max %.1f)  -> %.0f%% better overall, %.0f%% better beyond 14y" %
      (df.smooth_mae.mean(), df.smooth_le14.mean(), df.smooth_gt14.mean(), df.smooth_max.mean(),
       S["improvement_pct"], S["improvement_gt14_pct"]))
print("Par curve: exact %.2f bp, smoothed %.2f bp" % (df.exact_par_mae.mean(), df.smooth_par_mae.mean()))
