# Zero Coupon Yield Curve for Indian G-Secs

**Team:** Vaishnavreddy Bande · Yashas · Shubham · Aastha · Mansoor

A cubic-spline zero coupon yield curve (ZCYC) built from FBIL data, compared with FBIL's published
ZCYC on five dates (5, 14, 21, 28 August and 11 September 2026), and used to price the STRIPS of a
long-dated SDL under the RBI stripping guidelines (bonus task).

```bash
cd code
pip install -r requirements.txt
python app.py                                   # reproduces every table and chart, in order
python app.py --date 2026-09-11 --sdl IN2020250089   # one date end to end, with an HTML report
streamlit run streamlit_app.py                  # interactive app in the browser (see below)
node ../additional_material/deck_source/build_deck.js  # rebuilds the PowerPoint from the outputs
```

## Interactive app

`streamlit run streamlit_app.py` (from `code/`; if the `streamlit` command is not found, use
`python -m streamlit run streamlit_app.py`) opens the app at http://localhost:8501. It needs Python 3.10 or
newer and the packages in `requirements.txt`; nothing else. It uses the same engine as the scripts.

**Enter FBIL data for any date.** FBIL's Excel 97-2003 (`.xls`) files upload as they are and are converted internally (this uses the `xlrd` package from `requirements.txt`; if it is missing the app says so and shows the install command). Choose "Enter FBIL data for a new date" in the sidebar, then:

| Input | Needed? | What it gives |
|---|---|---|
| FBIL G-Sec valuation file | required | input bonds, prices and yields, FBIL's par curve; the valuation date is read from the file |
| T-bill rates (paste FBIL's table, or type `7 Days 4.72` lines) | required | the 7-day, 3M, 6M and 12M short-end knots |
| FBIL ZCYC and STRIPS file | optional | comparison with FBIL's zero curve (gap metrics, segment and date tabs) |
| FBIL SDL valuation file | optional | STRIPS of any SDL; without it any strippable G-Sec can still be stripped |

The files are checked before anything is stored (dates agree, enough input bonds, FBIL's prices reproduce from
its yields at some settlement date), and the app then opens the results for that date. Entered dates are saved in
`input_data/uploaded/` and can be removed from the sidebar. The settlement date is detected from the files, not assumed.

**Results.**
* **Sidebar:** date, exact fit / smoothed fit / both, sliders for λ and the slope (with a reset to the tuned values),
  and switches for the 3-month T-bill knot and the input-bond dots.
* **Tabs:** zero curve and par curve (against FBIL's when its file is loaded); gap by maturity segment; the same
  comparison on all dates (August tuning dates vs the held-out 11 Sep); input bonds with each curve's price error;
  STRIPS for any strippable SDL or G-Sec under the smoothed, exact or FBIL curve; CSV downloads.
* The curve refits in about 0.2 seconds, so the sliders respond immediately.

---

## 1. Results

Two curves are built from the same inputs: FBIL's flagged input bonds (26 to 30 per date, FRBs
excluded) plus the FBIL 7-day, 3-month, 6-month and 12-month T-bill rates. Both are natural cubic
splines on the semi-annual zero rate, so both are twice differentiable.

| Mean absolute gap to FBIL's published ZCYC (bp) | Exact-fit bootstrap | Smoothed fit (submitted) |
|---|---|---|
| All 200 tenors, average of 5 dates | 5.71 | 2.62 |
| Up to 14 years | **1.15** | 1.71 |
| Beyond 14 years | 7.49 | **2.97** |
| Worst tenor (average of 5 dates) | 24.3 | 12.1 |
| Par curve, all tenors | 1.49 | 0.94 |
| **11 Sep 2026 only (held out)** | 6.38 | **1.75** |

Read this table with two caveats:

* 144 of FBIL's 200 published tenors lie beyond 14 years, so the all-tenor average is dominated by
  the long end. **Up to 14 years the exact fit is closer to FBIL** (on 11 Sep: 1.21 vs 2.01 bp; up to
  10 years 0.59 vs 1.75 bp). The smoothed fit is weakest between 1 and 3 years, where there is no input
  bond between the 1-year T-bill and 2.6 years.
* The smoothing parameters were chosen by comparing against FBIL's curve on the four August dates
  (Section 3). Those four dates are therefore in-sample. Only 11 September is a held-out result.

**Leave-one-out test (does not use FBIL's curve at all).** Each interior input bond is dropped in
turn, the curve is refitted without it, and the bond is priced from the refitted curve. Over 129
hold-outs on the five dates, the smoothed fit misses the bond's published YTM by 2.45 bp on average,
against 3.90 bp for the exact fit (2.50 vs 4.16 bp up to 14 years, 2.36 vs 3.50 bp beyond). This is the
strongest independent evidence that smoothing improves the curve, not just its match to FBIL.

## 2. Why a smoothed fit

* **FBIL's own curve does not reprice FBIL's own input bonds.** Discounting each input bond on FBIL's
  published ZCYC misses its dirty price by 7.5 paise on average on 11 Sep (13.0 paise beyond 14 years).
* **Rounding does not explain it.** Our exact-fit curve reprices the inputs to 1e-13 rupees. Sampling it
  on FBIL's 0.25-year grid and rounding to two decimals raises that to 0.89 paise, about an eighth of
  FBIL's 7.5 paise.
* **FBIL's predecessor methodology says so.** Footnote 1 of the Concept Note in the assignment pack
  states that FIMMDA's method also uses an optimisation that minimises the cumulative difference between
  model and traded prices.
* **The exact fit's long-end error sits at the knots.** Beyond 14 years its gap to FBIL is 5.9 bp at the
  input maturities themselves and 8.4 bp across all tenors, so most of it is not interpolation error.
  Forcing the curve through every bond passes small inconsistencies between neighbouring bonds into the
  curve.

## 3. Method

**Exact-fit bootstrap (Task 2 as specified).** Knots at the four T-bill tenors plus one at each input
bond's maturity (30 knots on 11 Sep). The bond knots' zero rates are solved simultaneously so that every
bond's dirty price is matched exactly (max error 1.4e-13 rupees). The spline links neighbouring knots,
so the rates cannot be solved one bond at a time.

**Smoothed fit (submitted curve, a calibrated extension).** Same spline family on 22 fixed knots (fewer
than the 26 bonds), fitted by weighted least squares with a roughness penalty:

```
minimise   sum_i [ w_i ( model_price_i - market_dirty_price_i ) ]^2  +  sum_k [ sqrt(lambda(t_k)) * z''(t_k) ]^2
w_i        = 1 / (duration_i * price_i / 100)        a price error then behaves like a yield error
lambda(t)  = 0.005 * (1 + 0.5 t)                     penalty rises with maturity, where inputs thin out
knots      = T-bill tenors + {1.5, 2, 3, 4, 5, 6, 7, 8.5, 10, 12, 14, 17, 20, 24, 28, 33, 40, 50}
T-bill zero rates are imposed as hard constraints.
```

**How the two parameters were chosen.** `tune_and_checks.py` scores a 6 x 6 grid
(lambda 0.002 to 0.1, slope 0 to 1) against FBIL's published ZCYC on the four August dates and keeps
the lowest August average (2.83 bp). The chosen setting gives 1.75 bp on 11 September. This is a
calibration to FBIL for two numbers; the curve itself is built only from bond prices and T-bill rates.
The held-out result depends on the choice: the nine settings within 0.25 bp of the August best give
between 1.51 and 2.84 bp on 11 September.

**Shape checks, all five dates.** Discount factors strictly decreasing; 3-month forward rates between
5.7% and 10.2% (none negative); zero rates between 5.18% and 8.48%. Measured jump in the second
derivative across knots is numerically zero. The last input bond matures at about 49.4 years, so the
tenors from 49.5 to 50 years are a short extrapolation.

## 4. Conventions, each checked against FBIL's published output

| Convention | Evidence |
|---|---|
| Clean prices, **T+1 business-day settlement** | Recomputing FBIL's clean prices from its YTMs under each candidate settlement date: T+1 fits best on all five dates (0.03 to 0.08 paise). For 11 Sep that is **15 Sep**, because 14 Sep 2026 was a market holiday (Ganesh Chaturthi). |
| Semi-annual compounding, actual/actual accrual | Same test |
| Time to cash flow: actual days / 365.25 | Repricing FBIL's STRIPS from FBIL's ZCYC: act/365.25 1.01 paise, act/365 2.08, act/360 42.6, **30/360 0.85** (`daycount_check.csv`). 30/360 fits marginally better; the 0.16-paise difference is immaterial and we keep act/365.25. |
| T-bill rates used directly as zero rates at 0.25, 0.5, 1 year | FBIL's ZCYC equals them at those tenors (6M within 1 bp on three dates). Converting to bond-equivalent yields worsens the gap up to 14 years (1.70 vs 1.15 bp, `tbill_direct_vs_bey.csv`). |
| Par yield with pro-rated stub coupon | Applied to FBIL's zero curve it reproduces FBIL's par sheet to 0.87 bp at all 200 tenors |
| STRIP price = 100 x DF | FBIL's curve reproduces FBIL's ~1,595 published STRIPS (6 months or more) to 1.0 paise |

## 5. Bonus: STRIPS of 07.13 KL SGS 2058 (IN2020250089)

The longest of the 23 SDLs with coupon dates 2 January and 2 July (the dates the guidelines treat as
strippable); residual maturity 31.8 years. FBIL's SDL ZCYC stops at 14 years, so the STRIPS are
discounted on our smoothed G-Sec ZCYC.

1. **Cash flows:** 64 coupon STRIPS of 3.565 per Rs 100 of parent and one principal STRIP of 100.
2. **Present values:** PV = CF x DF(t), t = actual days / 365.25 from 15 Sep 2026.
3. **Normalise (para 15.2):** factor = min(book, market value) / sum of PVs. With book = market =
   dirty price 93.2857 (clean 91.8326 + accrued 1.4531) and sum of PVs 95.2256, the factor is 0.97963.
4. **Per STRIP:** price per Rs 100 face = 100 x normalised value / STRIP face; implied yield; face
   created per Rs 1 crore of parent (Rs 3,56,500 per coupon STRIP, Rs 1 crore principal).

Worked example, first coupon STRIP (GS02JAN2027C): t = 0.2984; zero rate 5.271%;
DF = (1 + 5.271/200)^(-2 x 0.2984) = 0.98459; PV = 3.5101; normalised 3.4386; price 96.4537 per Rs 100 face.
Principal STRIP (7.13%GS02JUL2058P): 7.5061 per Rs 100 face, 8.31% yield, 8.0% of the bond's value.
All 65 rows: `outputs/tables/strips_sdl2058_pricing.csv`.

**Checks.** Annex 4 of the guidelines is reproduced from its printed zero rates (sum of PVs 127.87,
factor 0.9384 vs 0.9385 printed). Pricing FBIL's ~1,595 published GOI STRIPS per date from our smoothed
curve gives 6.9 paise mean error (14.6 for the exact fit, 1.0 for FBIL's own curve). Because FBIL prices
its STRIPS from its ZCYC, this repeats the curve comparison in price terms; it is not an independent
market test.

**Findings.**
* The single normalisation factor cuts every STRIP by 2.0%. On the 0.3-year coupon STRIP that implies a
  12.5% yield against a 5.3% zero rate. A constant spread of 18.5 bp over the curve gives the same total
  value with a 5.5% short yield. This is our suggestion for discussion, not part of the guidelines.
* The factor depends on the discount curve: 0.9796 (ours), 0.9795 (FBIL G-Sec), 0.9814 (our exact fit),
  0.9820 (SDL curve held flat beyond 14 years), 1.0364 (SDL curve with its 50 bp 14-year spread carried
  forward). A factor above 1 means the curve discounts the cash flows to less than the bond's market
  price, i.e. the discount rates are too high for this bond; its own price implies about 18.5 bp over G-Secs.

**Assumptions.** Book value = market value. The 2058 SDL's published YTM (7.8289%) is FBIL's flat tenor
average for long SDLs, so the price fixes the total STRIPS value while the curve fixes how it is
distributed. The RBI guidelines name Government of India securities; we apply them to an SDL by analogy,
as FBIL's SDL methodology anticipates.

## 6. Differences from FBIL: what explains them

* **Methodology.** FBIL fits approximately with a smoothing step it does not disclose. It also selects
  inputs with trade-level rules (15 trades and Rs 75 crore over five days, spacing above 0.25 years)
  that need NDS-OM data we do not have; we use the input points FBIL flags, 7 of which (of 26 on 11 Sep)
  are FBIL proxy yields rather than trades.
* **Data accuracy.** FBIL publishes zero rates to two decimals (±0.5 bp). T-bill rates were transcribed
  by hand; the 6M rate is 1 bp below FBIL's curve on three dates.
* **Interpolation.** Changing the splined variable (discount function, forward rate) or the end condition
  does not fix the long end (`variant_comparison.csv`); the roughness penalty does.
* **Input sparsity.** 16 input bonds lie within 14 years and 10 cover the remaining 36, with gaps of
  7.2, 7.6 and 9.7 years.

## 7. Files

```
README.md                               this file
ZCYC_MiniProject_Presentation.pptx      presentation
code/app.py                             end-to-end entry point (all steps, or one date + HTML report)
code/streamlit_app.py                   interactive Streamlit app
code/src/appcore.py                     the app's logic (loading, fitting, tables, STRIPS, upload); no Streamlit imports
code/tune_and_checks.py                 smoothing-parameter grid, rounding control, day-count, T-bill and leave-one-out tests
code/run_all.py                         11-Sep analysis: conventions, exact fit and variants, smoothed fit, segment table
code/run_multidate.py                   five-date comparison; final curve table and charts
code/run_strips.py                      bonus task: STRIPS of the 2058 SDL
code/src/                               conventions, loaders, curve engine, STRIPS pricing
input_data/                             FBIL files for 11 Sep (unmodified) + T-bill screenshot
input_data/multi/                       FBIL files for all five dates + transcribed T-bill tables
input_data/uploaded/                    dates entered through the app (created on first use)
additional_material/outputs/tables/     result tables (final_curve_2026-09-11.csv is the Task 2 output)
additional_material/outputs/charts/     charts used in the deck
additional_material/outputs/app/        HTML reports written by app.py --date
additional_material/deck_source/        build_deck.js (rebuilds the PowerPoint)
additional_material/fbil_methodology/   FBIL G-Sec methodology v6 and SDL ZCYC methodology
```

## 8. Limitations

* FBIL's spline formulation, end conditions and smoothing step are not disclosed; we match its behaviour,
  not its algorithm.
* Two parameters are calibrated to FBIL's curve, and the held-out evidence is a single date.
* The smoothed fit is less accurate than the exact fit up to 10 years.
* Five dates over six weeks, with no change in the policy rate.
* Selecting the smoothing parameters by the leave-one-out test instead of FBIL's curve would remove the
  calibration entirely; we have not done this yet.

## 9. References

* FBIL, *G-Sec Valuation Methodology*, version 6 (6 October 2025) and August 2020 version
* FBIL, *SDL(SGS) ZCYC Methodology*, July 2022
* FBIL, *Concept Note: Revised G-Sec Valuation Methodology*
* RBI, *Guidelines on Stripping/Reconstitution of Government Securities*, IDMD.DOD.07/11.01.09
* Pienaar & Choudhry, *Fitting the term structure of interest rates: the practical implementation of cubic spline methodology*
