"""Interactive app: enter FBIL data for any date, get our zero coupon yield curve and STRIPS.

    cd code
    pip install -r requirements.txt
    streamlit run streamlit_app.py            (or: python -m streamlit run streamlit_app.py)

Same methodology as the submitted scripts (src/engine.py); the logic lives in src/appcore.py and this file is the interface.
"""
import os
import sys
import tempfile
import uuid
import warnings
from datetime import date

import matplotlib.pyplot as plt
import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
warnings.filterwarnings("ignore")
import appcore as ac  # noqa: E402

st.set_page_config(page_title="G-Sec zero coupon yield curve", layout="wide")

# Shared deployment: every visitor's uploads are private to that browser session, kept in a temporary folder and purged after a few hours.
MULTI_USER = ac.multiuser(__file__)
if MULTI_USER:
    ac.set_upload_dir(os.path.join(tempfile.gettempdir(), "zcyc_uploads"))
    st.session_state.setdefault("sid", uuid.uuid4().hex[:10])
SID = st.session_state.get("sid") if MULTI_USER else None

LAM0, SLOPE0 = ac.tuned_params()
st.session_state.setdefault("lam", LAM0)
st.session_state.setdefault("slope", SLOPE0)
st.session_state.setdefault("use_3m", True)
st.session_state.setdefault("show_bonds", True)
VIEW, ENTER = "Results for a loaded date", "Enter FBIL data for a new date"
st.session_state.setdefault("data_mode", VIEW)


def reset_smoothing():
    st.session_state["lam"] = LAM0
    st.session_state["slope"] = SLOPE0


def show(fig):
    st.pyplot(fig)
    plt.close(fig)


def csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8")


def build_date():
    """Runs when 'Build curve' is pressed: validate and store the entered files, then switch to the results."""
    ss = st.session_state
    ss.pop("form_error", None)
    try:
        gsec = ss.get("up_gsec")
        if gsec is None:
            raise ValueError("Upload the G-Sec valuation file.")
        gb = gsec.getvalue()
        typed = (ss.get("date_override") or "").strip()
        found = ac.file_date(gb)
        iso = typed or (found.isoformat() if found else "")
        if not iso:
            raise ValueError("The date could not be read from the file. Type it in the date box (YYYY-MM-DD).")
        try:
            date.fromisoformat(iso)
        except ValueError:
            raise ValueError("Enter the date as YYYY-MM-DD, for example 2026-09-18.")
        zc, sd = ss.get("up_zcyc"), ss.get("up_sdl")
        info = ac.save_upload(iso, gb, ac.parse_tbills(ss.get("tb_text", "")),
                              zc.getvalue() if zc is not None else None, sd.getvalue() if sd is not None else None, sid=SID)
        parts = [f"{info['n_inputs']} input bonds", f"settlement {info['settle']}",
                 "FBIL comparison included" if info["has_fbil"] else "no FBIL curve loaded, so no comparison",
                 "SDL STRIPS available" if info["has_sdl"] else "G-Sec STRIPS only"]
        ss["flash"] = f"Built the curve for {iso}: " + ", ".join(parts) + "."
        ss["iso_sel"] = info["key"]
        ss["data_mode"] = VIEW
    except ValueError as e:
        ss["form_error"] = str(e)


def remove_date():
    ac.delete_uploaded(st.session_state.get("iso_sel"))
    st.session_state.pop("iso_sel", None)


# ------------------------------------------------------------------ sidebar: what to do
sb = st.sidebar
sb.header("Settings")
sb.radio("What would you like to do?", [VIEW, ENTER], key="data_mode")

# ------------------------------------------------------------------ entering a new date
if st.session_state["data_mode"] == ENTER:
    st.title("Enter FBIL data for a new date")
    st.markdown(
        "Upload the Excel files FBIL publishes for that date (.xls or .xlsx) and paste the T-bill rates. The app reads the date from the files, "
        "fits our curve with the methodology of this project, and gives the zero curve, par curve and STRIPS.")
    if "form_error" in st.session_state:
        st.error(st.session_state["form_error"])
    st.subheader("1. Required")
    f1 = st.file_uploader("FBIL G-Sec valuation file (sheets 'G-Sec' and 'Par Yield')", type=["xlsx", "xls"], key="up_gsec")
    if f1 is not None:
        det, err = ac.describe_file(f1.getvalue())
        if err:
            st.error(f"G-Sec valuation file: {err}")
        else:
            st.caption(f"Date found in the file: {det}" if det else "No date found in the file; type it below.")
    st.text_area("FBIL T-bill rates: paste the table from FBIL's T-bill page, or type lines like '7 Days 4.72'", key="tb_text", height=150,
                 placeholder="7 Days   4.72\n3 Months   5.18\n6 Months   5.59\n12 Months   5.89")
    rates = ac.parse_tbills(st.session_state.get("tb_text", ""))
    need = [t for t in ac.REQUIRED_TBILLS if t not in rates]
    if rates:
        st.caption("Read: " + ", ".join(f"{k} {v:.2f}%" for k, v in rates.items()) +
                   (f".  Still needed: {', '.join(need)}" if need else ".  All four required rates found."))
    st.subheader("2. Optional")
    st.file_uploader("FBIL ZCYC and STRIPS file (sheets 'ZCYC' and 'STRIPS'): adds the comparison with FBIL's curve", type=["xlsx", "xls"], key="up_zcyc")
    st.file_uploader("FBIL SDL valuation file: lets you strip any SDL (without it, G-Secs can still be stripped)", type=["xlsx", "xls"], key="up_sdl")
    st.text_input("Valuation date, only if it could not be read from the file (YYYY-MM-DD)", key="date_override")
    st.button("Build curve", on_click=build_date, type="primary")
    st.caption("Files are checked before anything is stored: date match across files, enough input bonds, and that FBIL's prices "
               "reproduce from its yields at some settlement date. "
               + ("Your files are private to this browser session and are deleted after a few hours; only upload data you are allowed to share."
                  if MULTI_USER else "Entered dates are saved in input_data/uploaded/."))
    st.stop()

# ------------------------------------------------------------------ results for a loaded date
dates = ac.list_dates(SID)
if not dates:
    st.error("No FBIL data found in input_data/. Run the app from the project's code/ folder.")
    st.stop()
if st.session_state.get("iso_sel") not in dates:
    st.session_state["iso_sel"] = dates[-1]
role = lambda d_: "held out" if d_ == ac.HELD_OUT else ("tuning date" if d_ in ac.md.DATES else "entered by you")
iso = sb.selectbox("Valuation date", dates, key="iso_sel", format_func=lambda d_: f"{ac.base(d_)}  ({role(d_)})")
if ac.is_uploaded(iso):
    sb.button("Remove this entered date", on_click=remove_date)
choice = sb.radio("Curves to show", ["Both", "Smoothed fit", "Exact fit"])
keys = {"Both": ["exact", "smooth"], "Smoothed fit": ["smooth"], "Exact fit": ["exact"]}[choice]

sb.subheader("Smoothed fit")
sb.slider("λ: curvature penalty", min_value=0.001, max_value=0.100, step=0.001, format="%.3f", key="lam")
sb.slider("Slope: how fast the penalty grows with maturity", min_value=0.0, max_value=1.0, step=0.05, key="slope")
sb.button("Reset to the tuned values", on_click=reset_smoothing)
sb.caption(f"Tuned values: λ = {LAM0}, slope = {SLOPE0}, chosen on the four August dates. "
           "Lower λ fits the bonds more closely; higher λ gives a smoother curve.")
sb.subheader("Inputs")
sb.checkbox("Include the 3-month T-bill rate as a knot", key="use_3m")
sb.checkbox("Show input bond YTMs on the chart", key="show_bonds")
with sb.expander("About this app"):
    st.markdown(
        "**Exact fit:** natural cubic spline through the T-bill rates and every FBIL input bond; each bond reprices exactly.\n\n"
        "**Smoothed fit:** same spline family on a fixed knot grid, fitted by weighted least squares with a curvature "
        "penalty, so it need not pass through every bond. This is the submitted curve.\n\n"
        "**Comparison:** FBIL's published zero and par curves at 0.25-year tenors, when FBIL's ZCYC file is loaded. "
        "Gaps are our rate minus FBIL's, in basis points.\n\n"
        "**STRIPS:** present value of each cash flow on the chosen curve, then scaled by one factor so the STRIPS add up to the "
        "bond's price (RBI guidelines, para 15.2).")

lam, slope, use_3m = round(float(st.session_state["lam"]), 4), round(float(st.session_state["slope"]), 3), bool(st.session_state["use_3m"])
tuned_now = abs(lam - LAM0) < 1e-9 and abs(slope - SLOPE0) < 1e-9

if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))
st.title("Zero coupon yield curve for Indian G-Secs")
d = ac.load_inputs(iso)
n_t = int((d.inp["input_status"] == "T").sum())
n_p = int((d.inp["input_status"] == "Proxy").sum())
st.caption(f"Valuation date {ac.base(iso)} · settlement {d.settle} (detected from FBIL's prices) · {len(d.inp)} FBIL input bonds "
           f"({n_t} traded, {n_p} FBIL proxy yields) · T-bill inputs: 7-day, {'3M, ' if use_3m else ''}6M, 12M")
if not d.has_fbil:
    st.info("FBIL's ZCYC file is not loaded for this date, so there is no comparison with FBIL's zero curve. "
            "Our curve, STRIPS and downloads work as usual.")
with st.expander("How the settlement date was found"):
    st.dataframe(d.settle_table.rename(columns={"settle": "Candidate settlement date", "mean_paise": "Mean price error (paise)",
                                                "max_paise": "Largest price error (paise)"}).round(3), hide_index=True)
    st.caption("Each candidate is a business day after the valuation date. We recompute FBIL's clean prices from its YTMs "
               "on each candidate and keep the one that reproduces them best.")

curves, infos = {}, {}
for k in keys:
    try:
        curves[k], infos[k] = ac.fit_curve(iso, k, lam, slope, use_3m)
    except Exception as e:
        st.error(f"{ac.METHODS[k][0]} could not be fitted for {ac.base(iso)}: {e}")
if not curves:
    st.stop()
if "exact" in infos and not infos["exact"]["converged"]:
    st.warning("The exact-fit solver did not fully converge for this date; treat that curve with caution.")
if "smooth" in curves and lam < 0.003:
    st.warning("With a very small λ the smoothed fit approaches the exact fit and can oscillate in the long gaps between bonds.")
if "smooth" in curves and iso in ac.md.DATES and iso != ac.HELD_OUT and tuned_now and d.has_fbil:
    st.info("This is one of the four dates used to choose λ and the slope, so the smoothed-fit gap here is in-sample. "
            f"{ac.HELD_OUT} is the held-out date.")

tabs = {k: ac.curve_table(iso, c) for k, c in curves.items()}
for k, tab in tabs.items():
    st.subheader(ac.METHODS[k][0])
    cols = st.columns(5)
    if d.has_fbil:
        s = ac.summary(tab)
        cols[0].metric("Gap to FBIL, all tenors", f"{s['All tenors']:.2f} bp")
        cols[1].metric("Up to 14 years", f"{s['Up to 14 years']:.2f} bp")
        cols[2].metric("Beyond 14 years", f"{s['Beyond 14 years']:.2f} bp")
        cols[3].metric("Worst tenor", f"{s['Worst tenor']:.1f} bp")
        cols[4].metric("Par curve gap", f"{s['Par curve, all tenors']:.2f} bp" if "par_gap_bp" in tab else "n/a")
    else:
        for c_, (name, v) in zip(cols, ac.level_summary(tab).items()):
            c_.metric(name, f"{v:.2f}%")
if d.has_fbil:
    st.caption("Gap = average absolute difference between our zero curve and FBIL's published zero curve over the published tenors (lower is better).")

t_zero, t_par, t_seg, t_dates, t_bonds, t_strips, t_down = st.tabs(
    ["Zero curve", "Par curve", "Gap by segment", "All dates", "Input bonds", "STRIPS", "Downloads"])

# ------------------------------------------------------------------ zero curve
with t_zero:
    show(ac.fig_zero(iso, curves, show_bonds=bool(st.session_state["show_bonds"])))
    if d.has_fbil:
        st.caption("Top: FBIL's zero curve (navy) and ours (dashed), with input bond YTMs as teal dots. Bottom: our rate minus FBIL's in basis points; "
                   "the grey band is ±0.5 bp, FBIL's two-decimal rounding, and the dashed line marks 14 years.")
    else:
        st.caption("Our zero curve with the FBIL input bond YTMs as teal dots. Zero rates sit above the YTMs at long tenors because a YTM averages over all of a bond's coupons.")
    key_t = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 14, 20, 30, 40, 50]
    first = next(iter(tabs.values()))
    rows = first[first.tenor_years.isin(key_t)][["tenor_years"]].rename(columns={"tenor_years": "Tenor (years)"})
    if d.has_fbil:
        rows["FBIL zero %"] = first[first.tenor_years.isin(key_t)].fbil_zero_semi_annual_pct.to_numpy()
    for k, tab in tabs.items():
        sub = tab[tab.tenor_years.isin(key_t)]
        rows[f"{ac.METHODS[k][0]} zero %"] = sub.zero_semi_annual_pct.to_numpy()
        if d.has_fbil:
            rows[f"{ac.METHODS[k][0]} gap (bp)"] = sub.zero_gap_bp.to_numpy()
    st.dataframe(rows.round(3), hide_index=True)

# ------------------------------------------------------------------ par curve
with t_par:
    show(ac.fig_par(iso, curves))
    st.caption("The par yield is the coupon at which a bond prices at 100. It averages many zero rates, so it is calmer than the zero curve."
               + (" The same formula reproduces FBIL's par sheet from FBIL's own zero curve to within 0.87 bp." if d.par is not None else ""))

# ------------------------------------------------------------------ segments
with t_seg:
    if not d.has_fbil:
        st.info("Needs FBIL's ZCYC file for this date.")
    else:
        segs = {k: ac.segment_table(tab) for k, tab in tabs.items()}
        show(ac.fig_segments(segs))
        st.caption("Each bar is the average absolute gap to FBIL in one maturity band. On the study dates the exact fit is closest up to 10 years "
                   "and the smoothed fit is closest beyond 14 years, where most of FBIL's published tenors lie.")
        for k, t in segs.items():
            st.markdown(f"**{ac.METHODS[k][0]}**")
            st.dataframe(t.round(2), hide_index=True)

# ------------------------------------------------------------------ all dates
with t_dates:
    at = ac.all_dates_table(lam, slope, use_3m, SID)
    if at.empty:
        st.info("No date with FBIL's ZCYC file is loaded.")
    else:
        show(ac.fig_dates(at))
        st.caption("The same comparison on every date that has FBIL's zero curve, using the current λ, slope and T-bill setting. Teal shading marks the held-out date. "
                   "Move the sliders to see how the August (tuning) dates and the held-out date respond.")
        tune = at[at["Role"] == "tuning"]
        ho = at[at["Role"] == "held out"]
        if len(tune) and len(ho):
            c1, c2, c3 = st.columns(3)
            c1.metric("Smoothed fit, August average (tuning)", f"{tune['Smoothed fit: all'].mean():.2f} bp")
            c2.metric("Smoothed fit, held-out date", f"{ho['Smoothed fit: all'].iloc[0]:.2f} bp")
            c3.metric("Exact fit, held-out date", f"{ho['Exact-fit bootstrap: all'].iloc[0]:.2f} bp")
        st.dataframe(at.round(2), hide_index=True)

# ------------------------------------------------------------------ input bonds
with t_bonds:
    bt = ac.bond_table(iso, curves)
    st.dataframe(bt.round(4), hide_index=True)
    st.caption("Price error = model dirty price minus market dirty price, in paise per Rs 100. The exact fit is zero by construction; "
               "the smoothed fit misses each bond slightly, which is what lets it stay smooth. 'Proxy' bonds carry FBIL's proxy yield, not a trade.")

# ------------------------------------------------------------------ STRIPS
with t_strips:
    kinds = ["Government of India security (from the G-Sec file)"]
    if ac.sdl_path(iso) is not None:
        kinds.insert(0, "State Development Loan (from the SDL file)")
    else:
        st.caption("No SDL valuation file for this date, so only G-Secs can be stripped. Enter the date again with the SDL file to strip SDLs.")
    try:
        kind_label = st.radio("Security to strip", kinds, horizontal=True) if len(kinds) > 1 else kinds[0]
        kind = "sdl" if kind_label.startswith("State") else "gsec"
        secs = ac.list_securities(iso, kind)
        all_sec = st.checkbox("Include securities that the guidelines would not treat as strippable (coupon dates other than 2 Jan / 2 Jul)")
        pool = secs if all_sec else secs[secs["strippable"]]
        if pool.empty:
            st.info("No strippable security found. Tick the box above to price one anyway, for illustration.")
        else:
            labels = dict(zip(pool["isin"], pool["label"]))
            isin = st.selectbox("Security (longest first)", list(labels), format_func=lambda x: labels[x])
            opts = ["Smoothed fit (submitted)", "Exact fit"] + (["FBIL published G-Sec ZCYC"] if d.has_fbil else [])
            ck = st.radio("Discount curve", opts, horizontal=True)
            ckind = {"Smoothed fit (submitted)": "smooth", "Exact fit": "exact", "FBIL published G-Sec ZCYC": "fbil"}[ck]
            stp, info = ac.price_security(iso, kind, isin, ckind, lam, slope, use_3m)
            if not info["strippable"]:
                st.warning("The RBI guidelines allow stripping only for securities paying on 2 January and 2 July; this is shown for illustration.")
            st.markdown(f"**{info['description']}**: {info['n_coupon']} coupon STRIPS of {info['coupon'] / 2:.3f} per Rs 100 and one principal STRIP, "
                        f"{info['years']:.1f} years to maturity.")
            m = st.columns(5)
            m[0].metric("Clean + accrued", f"{info['clean']:.4f} + {info['accrued']:.4f}")
            m[1].metric("Dirty price (market value)", f"{info['dirty']:.4f}")
            m[2].metric("Sum of PVs on the curve", f"{info['sum_pv']:.4f}")
            m[3].metric("Normalisation factor", f"{info['factor']:.5f}")
            m[4].metric("Principal STRIP", f"{info['principal_price']:.4f} ({info['principal_yield']:.2f}%)")
            show(ac.fig_strips(stp, info))
            st.caption("Left: normalised value of each STRIP per Rs 100 of the bond. Right: price per Rs 100 face (navy) and implied yield (orange). "
                       "The single factor scales every STRIP so they add up to the bond's dirty price, which makes short STRIPS carry very high yields; "
                       "this is a feature of the guidelines' method.")
            out = stp[["strip_name", "strip_type", "date", "t_years", "cash_flow", "zero_pct", "discount_factor", "pv_unnormalised",
                       "normalised_value", "price_per_100_face", "implied_yield_semi_pct"]]
            st.dataframe(out.round(5), hide_index=True)
            st.download_button("Download STRIPS table (CSV)", data=csv_bytes(out), file_name=f"strips_{isin}_{ac.base(iso)}.csv", mime="text/csv")
    except Exception as e:
        st.error(f"Could not price STRIPS: {e}")

# ------------------------------------------------------------------ downloads
with t_down:
    st.markdown("Full curve tables: zero (semi-annual and annualised), par yield and discount factor"
                + (", with FBIL's values and the gaps." if d.has_fbil else "."))
    for k, tab in tabs.items():
        st.download_button(f"Download {ac.METHODS[k][0].lower()} curve for {ac.base(iso)} (CSV)", data=csv_bytes(tab.round(6)),
                           file_name=f"zcyc_{ac.base(iso)}_{k}.csv", mime="text/csv", key=f"dl_{k}")
        st.dataframe(tab.round(4), hide_index=True)
