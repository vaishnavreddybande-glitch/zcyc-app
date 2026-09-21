"""Bonus task: price the STRIPS of a long-dated SDL under the RBI Guidelines on Stripping/Reconstitution.

    python run_strips.py

PRIMARY discount curve = OUR OWN smoothed G-Sec ZCYC (built only from input bonds and T-bill rates).
FBIL's published curves appear only as comparisons / sensitivities, never as the primary input.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import brentq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
import multidate as md      # noqa: E402
import engine as en         # noqa: E402
import strips as sp         # noqa: E402
import data_loader as dl    # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "additional_material", "outputs")
TAB, CH = os.path.join(OUT, "tables"), os.path.join(OUT, "charts")
os.makedirs(TAB, exist_ok=True); os.makedirs(CH, exist_ok=True)
_P = json.load(open(os.path.join(OUT, "tuned_params.json")))   # written by tune_and_checks.py
LAM, SLOPE = _P["lam"], _P["slope"]
ISO = "2026-09-11"
SDL_ISIN = "IN2020250089"
NAVY, ORANGE, TEAL, GREY, RED = "#1F3A5F", "#E07B39", "#2A9D8F", "#8A8F98", "#C0392B"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "savefig.dpi": 190, "font.size": 11})
R = {}

# ------------------------------------------------------------------------------ curves for 11 Sep
settle, _ = md.detect_settlement(ISO)
g, tb, z = md.load_gsec(ISO), md.load_tbills(ISO), md.load_zcyc(ISO)
inp = g[g["is_input"] & ~g["is_frb"]]
own, _ = en.ls_fit(inp, tb, settle, lam=LAM, lam_slope=SLOPE)          # PRIMARY: our smoothed curve
exact, _ = en.bootstrap(inp, tb, settle, use_3m=True)                   # our exact-fit curve
FB = sp.published_curve(z, "cubic")                                     # FBIL G-Sec ZCYC: comparison only
sdlz = pd.read_excel(os.path.join(md.MULTI, f"sdl_zcyc_{ISO}.xlsx"), header=4)
sdlz.columns = ["tenor", "zero_semi", "zero_annual"]
SZ = sp.published_curve(sdlz.dropna(subset=["tenor"]), "cubic")         # FBIL SDL ZCYC (ends at 14y): sensitivity only

sdl = dl.load_sdl()
b = sdl[sdl["isin"] == SDL_ISIN].iloc[0]
acc = md.accrued(b.coupon, b.maturity, settle)
dirty = float(b.price + acc)
cfs = [(d, b.coupon / 2.0) for d, _ in md.cash_flows(b.coupon, b.maturity, settle)] + [(b.maturity, 100.0)]
face = np.r_[np.full(len(cfs) - 1, b.coupon / 2.0), 100.0]
tfn = lambda d: md.yearfrac(d, settle)
zown = lambda t: own.zero(np.asarray(t, float))
zex = lambda t: exact.zero(np.asarray(t, float))


def price(zero_fn):
    tab, fac = sp.price_strips(cfs, zero_fn, dirty, settle=settle, time_fn=tfn)
    tab["price100"] = 100.0 * tab["normalised_value"] / face
    tab["yield"] = sp.strip_yield_from_price(tab["price100"].to_numpy(), tab["t_years"].to_numpy())
    return tab, fac


primary, f_own = price(zown)
fbil_tab, f_fbil = price(FB)
exact_tab, f_exact = price(zex)
spr14 = float(SZ(14.0) - own.zero(14.0))
sdl_ext = lambda t: np.where(np.asarray(t, float) <= 14, SZ(np.minimum(np.asarray(t, float), 14.0)), own.zero(np.asarray(t, float)) + spr14)
sdl_flat = lambda t: np.where(np.asarray(t, float) <= 14, SZ(np.minimum(np.asarray(t, float), 14.0)), SZ(14.0))
ext_tab, f_ext = price(sdl_ext)
flat_tab, f_flat = price(sdl_flat)

# constant-spread alternative (not in the guidelines; offered for discussion)
tt = primary["t_years"].to_numpy(); zz = primary["zero_pct"].to_numpy(); cf = primary["cash_flow"].to_numpy()
s_star = brentq(lambda s: float(np.sum(cf * sp.cv.df_semiannual(zz + s, tt))) - dirty, -1.0, 3.0)
primary["alt_yield"] = zz + s_star
primary["alt_price100"] = 100.0 * sp.cv.df_semiannual(zz + s_star, tt)

# ------------------------------------------------------------------------------ tables
primary["strip"] = [("GS%sC" % d.strftime("%d%b%Y").upper()) if i < len(primary) - 1
                    else "%.2f%%GS%sP" % (b.coupon, d.strftime("%d%b%Y").upper())
                    for i, d in enumerate(primary["date"])]
primary["strip_type"] = ["Coupon"] * (len(primary) - 1) + ["Principal"]
primary["face_rs_per_1cr_parent"] = face / 100.0 * 1e7
out = primary.rename(columns={"price100": "strip_price_per_100_face", "yield": "strip_yield_semi_pct",
                              "alt_price100": "alt_strip_price_per_100_face", "alt_yield": "alt_strip_yield_semi_pct"})
out["strip_face_per_100_parent"] = face
cols = ["strip", "strip_type", "date", "t_years", "cash_flow", "zero_pct", "discount_factor", "pv_unnormalised",
        "normalised_value", "strip_face_per_100_parent", "strip_price_per_100_face", "strip_yield_semi_pct",
        "face_rs_per_1cr_parent", "alt_strip_price_per_100_face", "alt_strip_yield_semi_pct"]
out[cols].round(6).to_csv(os.path.join(TAB, "strips_sdl2058_pricing.csv"), index=False)

cmp_ = pd.DataFrame({"strip": out["strip"], "t_years": out["t_years"],
                     "price_own_smoothed_PRIMARY": primary["price100"],
                     "price_own_exact_fit": exact_tab["price100"],
                     "price_FBIL_published_comparison": fbil_tab["price100"]})
cmp_["own_minus_FBIL_paise"] = (cmp_["price_own_smoothed_PRIMARY"] - cmp_["price_FBIL_published_comparison"]) * 100
cmp_["exact_minus_FBIL_paise"] = (cmp_["price_own_exact_fit"] - cmp_["price_FBIL_published_comparison"]) * 100
cmp_.round(5).to_csv(os.path.join(TAB, "strips_sdl2058_curve_comparison.csv"), index=False)

sens = pd.DataFrame([
    ("A  PRIMARY: our smoothed G-Sec ZCYC", f_own, primary["price100"].iloc[-1], primary["price100"].iloc[0], primary["pv_unnormalised"].sum(),
     "Built only from input bonds and T-bills"),
    ("B  our exact-fit G-Sec ZCYC", f_exact, exact_tab["price100"].iloc[-1], exact_tab["price100"].iloc[0], exact_tab["pv_unnormalised"].sum(),
     "Earlier curve: overshoots at the long end"),
    ("C  FBIL published G-Sec ZCYC", f_fbil, fbil_tab["price100"].iloc[-1], fbil_tab["price100"].iloc[0], fbil_tab["pv_unnormalised"].sum(),
     "Comparison only (guidelines para 13 option)"),
    ("D  FBIL SDL ZCYC to 14y, then our G-Sec curve + 14y spread", f_ext, ext_tab["price100"].iloc[-1], ext_tab["price100"].iloc[0], ext_tab["pv_unnormalised"].sum(),
     "SDL curve ends at 14 years; sensitivity only"),
    ("E  FBIL SDL ZCYC to 14y, then flat", f_flat, flat_tab["price100"].iloc[-1], flat_tab["price100"].iloc[0], flat_tab["pv_unnormalised"].sum(),
     "Naive extension; sensitivity only"),
], columns=["discount_curve", "normalisation_factor", "principal_strip_price", "first_coupon_strip_price", "sum_of_pvs", "note"])
sens.round(5).to_csv(os.path.join(TAB, "strips_sdl2058_sensitivity.csv"), index=False)

# ------------------------------------------------------------------------------ validation across dates
a4, a4_factor, a4_sum, a4_norm = sp.annex4_check()
a4.round(6).to_csv(os.path.join(TAB, "annex4_reproduction.csv"), index=False)
vrows = []
for iso in md.DATES:
    s_, _ = md.detect_settlement(iso)
    gg, tb_, zz_ = md.load_gsec(iso), md.load_tbills(iso), md.load_zcyc(iso)
    ii = gg[gg["is_input"] & ~gg["is_frb"]]
    c_sm, _ = en.ls_fit(ii, tb_, s_, lam=LAM, lam_slope=SLOPE)
    c_ex, _ = en.bootstrap(ii, tb_, s_, use_3m=True)
    G_ = sp.published_curve(zz_, "cubic")
    st = md.load_strips(iso)
    t = np.array([md.yearfrac(m, s_) for m in st["maturity"]])
    m6 = t >= 0.5
    row = {"date": iso, "n_strips": int(m6.sum())}
    for name, fn in [("smooth", c_sm.zero), ("exact", c_ex.zero), ("fbil_control", G_)]:
        zz2 = np.asarray(fn(t[m6]), float)
        px = 100.0 * sp.cv.df_semiannual(zz2, t[m6])
        e = px - st["price"].to_numpy()[m6]
        y = (zz2 - st["yield_semi"].to_numpy()[m6]) * 100
        row[f"{name}_mae_paise"] = float(np.abs(e).mean() * 100)
        row[f"{name}_max_paise"] = float(np.abs(e).max() * 100)
        row[f"{name}_yield_mae_bp"] = float(np.abs(y).mean())
        long = t[m6] > 14
        row[f"{name}_mae_paise_gt14"] = float(np.abs(e[long]).mean() * 100)
    vrows.append(row)
val = pd.DataFrame(vrows)
val.round(4).to_csv(os.path.join(TAB, "strips_validation_multidate.csv"), index=False)

# ------------------------------------------------------------------------------ worked example
def wk(i):
    r = primary.iloc[i]
    return {"strip": r["strip"], "t": float(r["t_years"]), "cash_flow": float(r["cash_flow"]), "zero_pct": float(r["zero_pct"]),
            "df": float(r["discount_factor"]), "pv": float(r["pv_unnormalised"]), "normalised": float(r["normalised_value"]),
            "price100": float(r["price100"]), "yield": float(r["yield"])}

S = {"settle": str(settle), "valuation": ISO, "isin": SDL_ISIN, "desc": b.description, "coupon": float(b.coupon),
     "maturity": str(b.maturity), "clean": float(b.price), "accrued": float(acc), "dirty": dirty, "ytm": float(b.ytm),
     "n_cash_flow_dates": len(cfs) - 1, "n_coupon_strips": len(cfs) - 1, "n_strips": len(cfs),
     "sum_pv_own": float(primary["pv_unnormalised"].sum()), "factor_own": float(f_own),
     "factor_exact": float(f_exact), "factor_fbil": float(f_fbil), "factor_sdl_ext": float(f_ext), "factor_sdl_flat": float(f_flat),
     "spread14_bp": spr14 * 100, "implied_spread_bp": s_star * 100,
     "principal_price": float(primary["price100"].iloc[-1]), "principal_yield": float(primary["yield"].iloc[-1]),
     "principal_price_exact": float(exact_tab["price100"].iloc[-1]), "principal_price_fbil": float(fbil_tab["price100"].iloc[-1]),
     "principal_share_pct": float(100 * primary["normalised_value"].iloc[-1] / dirty),
     "first_price": float(primary["price100"].iloc[0]), "first_yield": float(primary["yield"].iloc[0]),
     "alt_first_yield": float(primary["alt_yield"].iloc[0]), "zero_first": float(primary["zero_pct"].iloc[0]),
     "sum_norm": float(primary["normalised_value"].sum()),
     "own_vs_fbil_mean_paise": float(cmp_["own_minus_FBIL_paise"].abs().mean()), "own_vs_fbil_max_paise": float(cmp_["own_minus_FBIL_paise"].abs().max()),
     "exact_vs_fbil_max_paise": float(cmp_["exact_minus_FBIL_paise"].abs().max()),
     "worked_first": wk(0), "worked_principal": wk(len(primary) - 1)}
V = {"val_smooth_mae_paise": float(val["smooth_mae_paise"].mean()), "val_exact_mae_paise": float(val["exact_mae_paise"].mean()),
     "val_fbil_mae_paise": float(val["fbil_control_mae_paise"].mean()), "val_smooth_max_paise": float(val["smooth_max_paise"].max()),
     "val_smooth_yield_bp": float(val["smooth_yield_mae_bp"].mean()), "val_exact_yield_bp": float(val["exact_yield_mae_bp"].mean()),
     "val_smooth_mae_gt14": float(val["smooth_mae_paise_gt14"].mean()), "val_exact_mae_gt14": float(val["exact_mae_paise_gt14"].mean()),
     "n_strips_per_date": int(val["n_strips"].mean())}
A4 = {"sum_pv": float(a4_sum), "factor": float(a4_factor), "sum_norm": float(a4_norm),
      "max_pv_diff": float(a4.pv_diff.abs().max()), "max_norm_diff": float(a4.norm_diff.abs().max())}
deck_rows = out[["strip", "strip_type", "t_years", "normalised_value", "strip_price_per_100_face", "strip_yield_semi_pct",
                 "alt_strip_yield_semi_pct", "zero_pct"]].round(4).to_dict(orient="records")
json.dump({"sdl": S, "validation": V, "annex4": A4, "rows": deck_rows, "sensitivity": sens.round(5).to_dict(orient="records"),
           "validation_by_date": val.round(4).to_dict(orient="records")},
          open(os.path.join(OUT, "strips_summary.json"), "w"), indent=2, default=float)

# ------------------------------------------------------------------------------ charts
fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
cs_, ps_ = out[out.strip_type == "Coupon"], out[out.strip_type == "Principal"]
ax[0].bar(cs_["t_years"], cs_["normalised_value"], width=0.35, color=TEAL, label="Coupon STRIPS (3.565 face each)")
ax[0].bar(ps_["t_years"], ps_["normalised_value"], width=0.6, color=ORANGE, label="Principal STRIP")
ax[0].set_xlabel("Years to cash flow"); ax[0].set_ylabel("Normalised value per Rs 100 of parent")
ax[0].set_title("Value of each STRIP per Rs 100 of the SDL", loc="left", fontsize=11); ax[0].legend(frameon=False)
ax[1].plot(out["t_years"], out["strip_price_per_100_face"], color=NAVY, marker="o", ms=3, label="Price per Rs 100 face")
ax[1].set_xlabel("Years to maturity of STRIP"); ax[1].set_ylabel("STRIP price per Rs 100 face")
a2 = ax[1].twinx()
a2.plot(out["t_years"], out["strip_yield_semi_pct"], color=ORANGE, lw=1.4, label="Yield, guidelines normalisation (right)")
a2.plot(out["t_years"], out["alt_strip_yield_semi_pct"], color=TEAL, lw=1.4, ls="--", label="Yield, constant-spread alternative (right)")
a2.set_ylabel("Yield, semi-annual (%)"); a2.grid(False); a2.spines["right"].set_visible(True)
h1, l1 = ax[1].get_legend_handles_labels(); h2, l2 = a2.get_legend_handles_labels()
ax[1].legend(h1 + h2, [x.replace(" (right)", "") for x in l1 + l2], frameon=False, fontsize=8, loc="upper center")
ax[1].set_title("Price per Rs 100 face and implied yield", loc="left", fontsize=11)
plt.tight_layout(); plt.savefig(os.path.join(CH, "05_strips_sdl2058.png")); plt.close()

fig, ax = plt.subplots(figsize=(9.5, 4.3))
x = np.arange(len(val)); w = 0.27
ax.bar(x - w, val["exact_mae_paise"], w, color=GREY, label="Our exact-fit curve")
ax.bar(x, val["smooth_mae_paise"], w, color=ORANGE, label="Our smoothed curve (used for the SDL)")
ax.bar(x + w, val["fbil_control_mae_paise"], w, color=NAVY, label="FBIL's own curve (control)")
ax.set_xticks(x); ax.set_xticklabels([d[5:].replace("-", "/") for d in val["date"]])
ax.set_ylabel("Mean error pricing FBIL's STRIPS (paise per Rs 100 face)")
ax.set_title("FBIL's published GOI STRIPS repriced from each curve (STRIPS of 6 months or more)", loc="left", fontsize=11); ax.legend(frameon=False, fontsize=9)
plt.tight_layout(); plt.savefig(os.path.join(CH, "09_strips_validation_multidate.png")); plt.close()

print("Settlement %s | dirty %.4f | sum PV %.4f | factor %.5f (own smoothed)" % (settle, dirty, S["sum_pv_own"], f_own))
print("Principal STRIP: own %.4f | exact-fit %.4f | FBIL %.4f" % (S["principal_price"], S["principal_price_exact"], S["principal_price_fbil"]))
print("Own vs FBIL-curve STRIP prices: mean %.1f paise, max %.1f paise (exact-fit max %.1f)" % (S["own_vs_fbil_mean_paise"], S["own_vs_fbil_max_paise"], S["exact_vs_fbil_max_paise"]))
print("Sum of normalised values %.4f vs dirty %.4f" % (S["sum_norm"], dirty))
print(sens[["discount_curve", "normalisation_factor", "principal_strip_price"]].round(4).to_string(index=False))
print("\nVALIDATION pricing FBIL's STRIPS (>=6M), mean paise across 5 dates:  smooth %.1f | exact %.1f | FBIL control %.1f ; smooth yield err %.2f bp" %
      (V["val_smooth_mae_paise"], V["val_exact_mae_paise"], V["val_fbil_mae_paise"], V["val_smooth_yield_bp"]))
print(val[["date", "n_strips", "smooth_mae_paise", "exact_mae_paise", "fbil_control_mae_paise", "smooth_max_paise"]].round(2).to_string(index=False))
