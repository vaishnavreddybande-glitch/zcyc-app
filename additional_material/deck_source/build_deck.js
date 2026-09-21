// Builds the presentation in the assignment's task order. Every number is read from the JSON/CSV outputs.
// Run after `python code/app.py`:   node additional_material/deck_source/build_deck.js
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.join(__dirname, "..", "..");
const OUT = path.join(ROOT, "additional_material", "outputs");
const CH = path.join(OUT, "charts");
const J = (f) => JSON.parse(fs.readFileSync(path.join(OUT, f), "utf8"));
const R = J("results_summary.json"), M = J("multidate_summary.json"), ST = J("strips_summary.json"), C = J("checks_summary.json");
const SD = ST.sdl, VAL = ST.validation, A4 = ST.annex4;
const f = (x, d = 2) => Number(x).toFixed(d);
const seg = (name) => R.segments.find((s) => s.segment_years === name);
const V = (k) => R.variants.find((v) => v.variant.startsWith(k));
const PD = M.per_date;

const INK = "0F2A33", TEAL = "1B6F7A", MINT = "E6F1F2", AMBER = "E8A33D", MUTED = "55666E",
      WHITE = "FFFFFF", PALE = "F6FAFA", SAND = "FDF3E3";
const HEAD = "Cambria", BODY = "Calibri";
const MG = 0.6, SW = 13.333, W = SW - 2 * MG;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "Zero Coupon Yield Curve for Indian G-Secs";

// ---------------------------------------------------------------- helpers
function pngSize(file) { const b = fs.readFileSync(file); return [b.readUInt32BE(16), b.readUInt32BE(20)]; }
function title(s, t, step) {
  if (step) s.addText(step, { x: MG, y: 0.3, w: W, h: 0.3, fontFace: BODY, fontSize: 12, color: AMBER, bold: true,
                              charSpacing: 1, margin: 0, isTextBox: true });
  s.addText(t, { x: MG, y: step ? 0.6 : 0.4, w: W, h: 0.65, fontFace: HEAD, fontSize: 28, bold: true, color: INK,
                 margin: 0, isTextBox: true, valign: "top" });
}
function body(s, t, o) {
  s.addText(t, Object.assign({ fontFace: BODY, fontSize: 14, color: INK, margin: 0, isTextBox: true, valign: "top" }, o));
}
function card(s, x, y, w, h, fill) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill || MINT }, line: { color: fill || MINT }, rectRadius: 0.08 });
}
// text block with optional headings: items are strings (bullets) or {h: "Heading"} or {p: "plain paragraph"}
function block(s, items, o) {
  const arr = [];
  items.forEach((it, i) => {
    const last = i === items.length - 1;
    if (typeof it === "object" && it.h) arr.push({ text: it.h, options: { bold: true, fontFace: HEAD, fontSize: (o.fontSize || 13) + 2, color: TEAL, breakLine: !last, paraSpaceAfter: 4, paraSpaceBefore: i ? 8 : 0 } });
    else if (typeof it === "object" && it.p) arr.push({ text: it.p, options: { breakLine: !last, paraSpaceAfter: 6 } });
    else arr.push({ text: it, options: { bullet: { indent: 14 }, breakLine: !last, paraSpaceAfter: 5 } });
  });
  s.addText(arr, Object.assign({ fontFace: BODY, fontSize: 13, color: INK, margin: 0, isTextBox: true, valign: "top" }, o));
}
function tbl(s, rows, o) {
  const fs_ = o.fontSize || 11.5;
  const hdr = (t) => ({ text: t, options: { bold: true, color: WHITE, fill: { color: TEAL }, fontFace: BODY, fontSize: fs_ } });
  const cel = (c, al) => ({ text: typeof c === "object" ? c.t : String(c),
                            options: { fontFace: BODY, fontSize: fs_, color: INK, bold: typeof c === "object" && !!c.b, align: al } });
  const data = rows.map((r, i) => r.map((c, j) => (i === 0 ? hdr(c) : cel(c, (o.right || []).includes(j) ? "right" : "left"))));
  s.addTable(data, Object.assign({ border: { type: "solid", color: "D5E3E5", pt: 1 }, valign: "middle", margin: 0.06 }, o));
}
function image(s, file, x, y, maxW, maxH) {
  const p = path.join(CH, file); const [pw, ph] = pngSize(p);
  let w = maxW, h = maxW * ph / pw;
  if (h > maxH) { h = maxH; w = maxH * pw / ph; }
  s.addImage({ path: p, x, y, w, h });
  return { w, h };
}
// chart on the left, explanation panel on the right
function chartSlide(step, t, file, read, shows, notes, extra) {
  const s = pres.addSlide(); s.background = { color: WHITE };
  title(s, t, step);
  const im = image(s, file, MG, 1.45, 7.9, extra && extra.maxH ? extra.maxH : 5.6);
  card(s, 8.75, 1.45, SW - MG - 8.75, 5.65, PALE);
  const panel = extra && extra.panel ? extra.panel : [{ h: "How to read it" }, ...read, { h: "What it shows" }, ...shows];
  block(s, panel, { x: 8.98, y: 1.62, w: SW - MG - 9.2, h: 5.35, fontSize: extra && extra.fs ? extra.fs : 13 });
  const below = 1.45 + im.h + 0.2;
  if (extra && extra.takeaway) {
    card(s, MG, below, 7.9, 7.1 - below, SAND);
    block(s, extra.takeaway, { x: MG + 0.25, y: below + 0.15, w: 7.4, h: 7.1 - below - 0.25, fontSize: 14, valign: "middle" });
  }
  if (notes) s.addNotes(notes);
  return { s, im, below };
}
function section(n, t, points) {
  const s = pres.addSlide(); s.background = { color: INK };
  s.addText("TASK " + n, { x: MG, y: 2.5, w: 6, h: 0.4, fontFace: BODY, fontSize: 15, color: AMBER, margin: 0, isTextBox: true, charSpacing: 2 });
  s.addText(t, { x: MG, y: 2.95, w: 7.2, h: 1.5, fontFace: HEAD, fontSize: 40, bold: true, color: WHITE, margin: 0, isTextBox: true });
  const arr = points.map((p, i) => ({ text: `Step ${i + 1}   ${p}`, options: { breakLine: i < points.length - 1, paraSpaceAfter: 10 } }));
  s.addText(arr, { x: 7.9, y: 2.6, w: 4.9, h: 3, fontFace: BODY, fontSize: 15, color: "BFDDE1", margin: 0, isTextBox: true, valign: "top" });
}
function steps(s, items, y, h) {   // numbered step cards in a row
  const n = items.length, gap = 0.22, w = (W - gap * (n - 1)) / n;
  items.forEach((it, i) => {
    const x = MG + i * (w + gap);
    card(s, x, y, w, h, i % 2 ? PALE : MINT);
    s.addShape(pres.shapes.OVAL, { x: x + 0.22, y: y + 0.22, w: 0.46, h: 0.46, fill: { color: TEAL }, line: { color: TEAL } });
    s.addText(String(i + 1), { x: x + 0.22, y: y + 0.22, w: 0.46, h: 0.46, fontFace: HEAD, fontSize: 16, bold: true, color: WHITE,
                               align: "center", valign: "middle", margin: 0, isTextBox: true });
    body(s, it[0], { x: x + 0.22, y: y + 0.8, w: w - 0.44, h: 0.4, fontSize: 15, bold: true, fontFace: HEAD });
    body(s, it[1], { x: x + 0.22, y: y + 1.22, w: w - 0.44, h: h - 1.35, fontSize: 13, color: MUTED });
  });
}

// ================================================================ 1 TITLE
{
  const s = pres.addSlide(); s.background = { color: INK };
  s.addText("Zero Coupon Yield Curve\nfor Indian G-Secs", { x: MG, y: 1.6, w: 8, h: 1.9, fontFace: HEAD, fontSize: 42, bold: true,
    color: WHITE, margin: 0, isTextBox: true, valign: "top" });
  s.addText("Cubic-spline bootstrap from FBIL data, comparison with FBIL's published curve, and STRIPS pricing for a 2058 SDL",
    { x: MG, y: 3.65, w: 7.6, h: 1.0, fontFace: BODY, fontSize: 17, color: "BFDDE1", margin: 0, isTextBox: true });
  s.addText("Vaishnavreddy Bande · Yashas · Shubham · Aastha · Mansoor", { x: MG, y: 5.9, w: 8, h: 0.4, fontFace: BODY, fontSize: 15, color: "BFDDE1", margin: 0, isTextBox: true });
  s.addText("Mini Project 1  |  FBIL data for 5, 14, 21, 28 August and 11 September 2026", { x: MG, y: 6.4, w: 8, h: 0.4, fontFace: BODY, fontSize: 13, color: "8FB8BE", margin: 0, isTextBox: true });
}

// ================================================================ 2 AGENDA
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  title(s, "How the presentation is organised");
  const items = [
    ["1", "Data collection", "FBIL G-Sec prices and yields, published ZCYC and STRIPS, T-bill rates, SDL data", "Slides 4–5"],
    ["A", "Exact-fit bootstrap (Tasks 2 and 3)", "Method, output curves, comparison with FBIL, where and why it fails", "Slides 7–13"],
    ["B", "Smoothed fit (Tasks 2 and 3)", "The same six steps for the submitted curve", "Slides 15–20"],
    ["C", "Exact or smoothed? (Task 3)", "Side-by-side results, a test without FBIL, causes of the remaining gap", "Slides 22–25"],
    ["4", "Bonus: pricing STRIPS", "07.13 KL SGS 2058 stripped and priced under the RBI guidelines; checks", "Slides 27–30"],
  ];
  items.forEach((it, i) => {
    const y = 1.35 + i * 1.12;
    card(s, MG, y, W, 0.98, i % 2 ? PALE : MINT);
    s.addShape(pres.shapes.OVAL, { x: MG + 0.28, y: y + 0.21, w: 0.55, h: 0.55, fill: { color: TEAL }, line: { color: TEAL } });
    s.addText(it[0], { x: MG + 0.28, y: y + 0.21, w: 0.55, h: 0.55, fontFace: HEAD, fontSize: 20, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0, isTextBox: true });
    body(s, it[1], { x: MG + 1.05, y: y + 0.17, w: 6, h: 0.4, fontSize: 17, bold: true, fontFace: HEAD });
    body(s, it[2], { x: MG + 1.05, y: y + 0.55, w: 8.8, h: 0.4, fontSize: 12.5, color: MUTED });
    body(s, it[3], { x: W - 1.2, y: y + 0.3, w: 1.6, h: 0.4, fontSize: 13, color: TEAL, bold: true });
  });
}

// ================================================================ TASK 1
section("1", "Data Collection", ["Files collected from FBIL", "Conventions checked against FBIL"]);
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  title(s, "Files collected from FBIL", "TASK 1  ·  STEP 1");
  tbl(s, [
    ["FBIL file (each date)", "What we use"],
    ["G-Sec prices and yields", `${R.n_gsec_fixed} fixed-coupon G-Secs with coupon, maturity, clean price and YTM. The remark column marks FBIL's input points (${R.n_inputs} on 11 Sep: ${R.n_inputs_traded} traded, ${R.n_inputs_proxy} FBIL proxy yields). ${R.n_frb} FRBs excluded.`],
    ["ZCYC and STRIPS", "FBIL's zero and par curves at 200 tenors from 0.25 to 50 years (the benchmark), and about 1,600 published GOI STRIP prices"],
    ["T-bill rates", "7-day to 12-month FBIL rates. The 7-day, 3M, 6M and 12M rates are the short-end inputs, as in FBIL methodology v6"],
    ["SDL valuation and SDL ZCYC", "5,438 state securities for the bonus task. FBIL's SDL curve stops at 14 years"],
  ], { x: MG, y: 1.5, w: 7.7, colW: [2.2, 5.5], fontSize: 13.5, rowH: [0.45, 1.25, 1.0, 1.0, 0.9] });
  card(s, 8.6, 1.5, SW - MG - 8.6, 5.3, MINT);
  block(s, [{ h: "Choices we made" },
    "11 September 2026 is the latest date available: FBIL publishes these files free with a seven-day lag.",
    "Four August dates were added so results can be checked across time rather than on a single day.",
    "FRBs, inflation-indexed and special securities are left out because their cash flows are not fixed.",
    "T-bill rates were copied from FBIL's website by hand; a screenshot for 11 Sep is in the input folder."],
    { x: 8.85, y: 1.7, w: SW - MG - 9.1, h: 5, fontSize: 14 });
}
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  title(s, "Pricing conventions, checked against FBIL's own numbers", "TASK 1  ·  STEP 2");
  const dc = C.daycount_mean_paise;
  tbl(s, [
    ["Convention", "Test", "Result"],
    ["Clean prices, T+1 business-day settlement", "Recompute FBIL's clean prices from its YTMs for each candidate settlement date", { t: `T+1 best on all five dates (0.03–0.08 paise). For 11 Sep this is 15 Sep: 14 Sep was a market holiday`, b: true }],
    ["Time in years = actual days / 365.25", "Reprice FBIL's STRIPS from FBIL's ZCYC under four day-count bases", `act/365.25 ${f(dc["act/365.25"])} paise, act/365 ${f(dc["act/365"])}, act/360 ${f(dc["act/360"], 1)}, 30/360 ${f(dc["30/360"])}. 30/360 is marginally closer; we keep act/365.25`],
    ["T-bill rates used directly as zero rates", "Compare with FBIL's ZCYC at 0.25, 0.5 and 1 year; try bond-equivalent conversion", `Equal at those tenors (6M within 1 bp). Conversion worsens the fit up to 14y: ${f(C.tbill_le14_bp.bond_equivalent)} vs ${f(C.tbill_le14_bp.direct)} bp`],
    ["Par yield with a pro-rated first coupon", "Apply the formula to FBIL's zero curve and compare with FBIL's par sheet", { t: `All 200 tenors within ${f(R.par_formula_check.max_bp)} bp`, b: true }],
    ["STRIP price = 100 × discount factor", "Price FBIL's STRIPS from FBIL's ZCYC", `Mean error ${f(R.strips_val.mae_paise)} paise over ${R.strips_val.n} STRIPS`],
  ], { x: MG, y: 1.5, w: W, colW: [3.1, 4.4, 4.63], fontSize: 13.5, rowH: [0.45, 0.95, 0.95, 0.95, 0.8, 0.7] });
  s.addNotes("If a convention is wrong, the error hides inside the curve and looks like a methodology difference. That is why each one was tested against a number FBIL published.");
}

// ================================================================ PART A: EXACT FIT
const EX = M.methods.exact, SM = M.methods.smooth, o = M.oos;
const sg = (m, k) => m.segments[k];
function partDivider(tag, t, points) {
  const s = pres.addSlide(); s.background = { color: INK };
  s.addText(tag, { x: MG, y: 2.5, w: 7, h: 0.4, fontFace: BODY, fontSize: 15, color: AMBER, margin: 0, isTextBox: true, charSpacing: 2 });
  s.addText(t, { x: MG, y: 2.95, w: 7.2, h: 1.5, fontFace: HEAD, fontSize: 40, bold: true, color: WHITE, margin: 0, isTextBox: true });
  const arr = points.map((p, i) => ({ text: `Step ${i + 1}   ${p}`, options: { breakLine: i < points.length - 1, paraSpaceAfter: 10 } }));
  s.addText(arr, { x: 7.9, y: 2.3, w: 4.9, h: 3.6, fontFace: BODY, fontSize: 15, color: "BFDDE1", margin: 0, isTextBox: true, valign: "top" });
}
function outputSlide(tag, t, file, m, read, shows) {
  const cp = m.curve_points, T = ["0.25", "1", "2", "5", "10", "14", "20", "30", "40", "50"];
  const { s, im } = chartSlide(tag, t, file, read, shows, null, { maxH: 4.1, fs: 12 });
  tbl(s, [["Tenor", ...T.map((k) => k + "y")], ["Zero, s.a. %", ...T.map((k) => f(cp[k].zero_sa))], ["Par, s.a. %", ...T.map((k) => f(cp[k].par_sa))]],
    { x: MG, y: 1.45 + im.h + 0.2, w: 7.9, colW: [1.3, ...Array(10).fill(6.6 / 10)], fontSize: 11, right: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] });
}
const READ_CURVES = ["x-axis: residual maturity in years; y-axis: rate in % a year",
  "Solid navy: zero rate, semi-annual compounding. Teal dash-dot: the same rate annualised, (1 + z/2)² − 1",
  "Orange dashed: par yield. Grey dots: input bond YTMs. Red squares: the four T-bill inputs"];
const READ_ZERO = (lbl) => [`Top: FBIL's zero curve (navy), the ${lbl} (dashed) and the input bond YTMs (teal dots)`,
  "Bottom: our rate minus FBIL's in basis points. Grey band: ±0.5 bp, FBIL's 2-decimal rounding. Dashed line: 14 years",
  "Axes are identical in Parts A and B"];
const READ_PAR = (lbl) => [`Top: FBIL's par yield (navy) and the par yield computed from the ${lbl} (dashed)`,
  "Bottom: difference in bp, grey band ±0.5 bp. Same scale in Parts A and B",
  "Par yield = the coupon that prices a bond at 100 today; our formula reproduces FBIL's par sheet from FBIL's own zero curve to 0.87 bp"];
const READ_ACC = ["Left: average absolute gap to FBIL in each maturity band on 11 Sep. Dashed line: 14 years",
  "Right: the same gap on each of the five dates, for all tenors (dark), up to 14 years (medium) and beyond 14 years (light)",
  "Same scales in Parts A and B"];
const READ_LONG = (lbl) => [`FBIL's zero curve (navy) and the ${lbl} (dashed) beyond 14 years`,
  "Teal lines: maturities of the 10 input bonds beyond 14 years. Shaded: stretches of more than 5 years with no input bond"];

partDivider("PART A  ·  TASKS 2 AND 3", "Exact-fit bootstrap", ["Method", "Output curves", "Zero curve vs FBIL", "Par curve vs FBIL", "Gap by segment and date", "The long end", "Why it fails beyond 14 years"]);
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  title(s, "Method: exact-fit cubic-spline bootstrap", "PART A  ·  EXACT FIT  ·  STEP 1");
  steps(s, [
    ["Place the knots", `Fixed knots at the 7-day, 3M, 6M and 12M T-bill rates, plus one knot at each input bond's maturity: ${R.exact.n_knots} knots on 11 Sep.`],
    ["One equation per bond", "Each bond's cash flows, discounted on the spline, must equal its dirty price (FBIL clean price plus accrued interest)."],
    ["Solve together", "A spline links neighbouring knots, so the knot rates cannot be found one bond at a time. A root-finder solves all of them at once."],
    ["Natural cubic spline", "Rate, slope and curvature are continuous at every knot, so the curve is twice differentiable by construction."],
  ], 1.5, 2.9);
  card(s, MG, 4.65, W, 2.15, SAND);
  block(s, [{ h: "What this gives" },
    `A curve that passes exactly through every input: each bond reprices to within ${Number(R.exact.max_price_error).toExponential(1)} rupees and each T-bill rate is hit exactly.`,
    `The measured jump in the second derivative across knots is ${Number(R.exact.d2_jump).toExponential(0)}, i.e. zero, so the curve is twice differentiable as the assignment requires.`],
    { x: MG + 0.3, y: 4.85, w: W - 0.6, h: 1.85, fontSize: 14.5 });
  s.addNotes("This is the method the assignment asks for. The next slides show what it produces and how it compares with FBIL.");
}
outputSlide("PART A  ·  EXACT FIT  ·  STEP 2", "Output: zero and par curves from the exact fit", "exact_1_curves.png", EX, READ_CURVES,
  [`Starts at the T-bill rates (5.18% at 3 months) and rises to ${f(EX.curve_points["2"].zero_sa)}% at 2 years and ${f(EX.curve_points["10"].zero_sa)}% at 10 years`,
   `Beyond 20 years the zero curve wobbles: a bump near 27 years, a dip near 29, then a peak of ${f(EX.peak[1])}% at ${f(EX.peak[0], 1)} years before falling to ${f(EX.curve_points["40"].zero_sa)}% at 40`,
   "The zero curve sits above the par curve and the YTMs at long tenors: on a rising curve, a single far cash flow needs a higher rate than a bond's average yield",
   "The par curve is much calmer than the zero curve because each par yield averages many zero rates"]);
chartSlide("PART A  ·  EXACT FIT  ·  STEP 3", "Exact fit against FBIL's zero curve", "exact_2_vs_fbil.png", READ_ZERO("exact fit"),
  [`Up to 14 years the two curves are close: ${f(EX.mae_le14)} bp average gap, largest ${f(EX.max_le14, 1)} bp`,
   `Beyond 14 years the gap averages ${f(EX.mae_gt14)} bp and swings between about −12 and +${f(EX.max_gt14, 0)} bp, peaking at ${EX.max_at} years`,
   `Over all 200 tenors: ${f(EX.mae)} bp average; only ${f(EX.within_2bp_pct, 0)}% of tenors are within 2 bp of FBIL`,
   "The swings line up with where input bonds are sparse (Step 6)"], null, { fs: 12.5 });
chartSlide("PART A  ·  EXACT FIT  ·  STEP 4", "Exact fit: par yield against FBIL", "exact_3_par.png", READ_PAR("exact fit"),
  [`Average par gap ${f(EX.par_mae)} bp; largest ${f(EX.par_max, 1)} bp at ${EX.par_max_at} years`,
   "Up to 12 years the par curves agree within about 1 bp",
   "The zero-curve swings beyond 14 years show up again here, reduced to −6 to +4 bp because a par yield averages them",
   "After 38 years the par gap is almost zero even though the zero gap is about −10 bp: the par yield there is dominated by earlier coupons"], null, { fs: 12.5 });
{
  const x = (k) => f(sg(EX, k), 1), pd = (k) => PD.map((d) => d[k]);
  chartSlide("PART A  ·  EXACT FIT  ·  STEP 5", "Exact fit: gap to FBIL by segment and by date", "exact_4_accuracy.png", READ_ACC,
    [`By segment (11 Sep): under 1 bp in every band up to 10 years, ${x("10-14")} bp at 10–14, then ${x("14-20")}, ${x("20-30")}, ${x("30-40")} and ${x("40-50")} bp in the bands beyond`,
     `By date: up to 14 years ${f(Math.min(...pd("exact_le14")))}–${f(Math.max(...pd("exact_le14")))} bp on every date; beyond 14 years ${f(Math.min(...pd("exact_gt14")))}–${f(Math.max(...pd("exact_gt14")))} bp`,
     `Five-date average: ${f(M.mean_exact_le14)} bp up to 14 years, ${f(M.mean_exact_gt14)} bp beyond`,
     "The pattern repeats on every date, so the long-end problem is structural, not one bad day"],
    null, { maxH: 4.3, fs: 12.5, takeaway: [{ p: "The exact fit is the better match to FBIL up to 10 years. Beyond 14 years, where 144 of FBIL's 200 published tenors lie, it is consistently several basis points off." }] });
}
chartSlide("PART A  ·  EXACT FIT  ·  STEP 6", "Exact fit: the long end", "exact_5_long_end.png", READ_LONG("exact fit"),
  [`In the 7.6-year gap between 30.0 and 37.6 years the curve bulges to ${f(EX.peak[1])}%, about ${f(EX.max, 0)} bp above FBIL`,
   "It then drops below FBIL and stays about 10 bp under it to 50 years",
   "Around 27–29 years four bonds sit close together; small differences in their yields make the curve kink up and down",
   "A cubic spline forced through every point overshoots between widely spaced knots"],
  null, { maxH: 4.3, fs: 12.5, takeaway: [{ p: "Where bonds are far apart the exact fit overshoots; where they are close together it picks up noise between them. Both effects come from forcing the curve through every bond." }] });
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  title(s, "Why the exact fit fails beyond 14 years", "PART A  ·  EXACT FIT  ·  STEP 7");
  const rc = C.rounding_control, fr = R.fbil_repricing;
  tbl(s, [
    ["Check (11 September)", "Result", "What it means"],
    ["Where the exact fit's long-end gap sits", `${f(R.exact_gap_at_input_maturities_gt14_bp, 1)} bp at the input maturities, ${f(R.exact_vs_fbil.mae_gt14, 1)} bp across all tenors beyond 14y`, "Most of the gap is at the knots themselves, so better interpolation alone cannot remove it"],
    ["Price FBIL's own input bonds on FBIL's published ZCYC", { t: `Mean error ${f(fr.mean_paise, 1)} paise (${f(fr.gt14_paise, 1)} beyond 14 years)`, b: true }, "FBIL's curve does not pass through its own inputs"],
    ["Same test after rounding our exact curve to 2 decimals on FBIL's 0.25-year grid", `${f(rc.exact_fit_rounded_to_fbil_grid_paise, 2)} paise`, "Rounding explains only about an eighth of FBIL's error"],
    ["FBIL Concept Note, footnote 1", "FIMMDA's model also minimises the total gap between model and traded prices", "The predecessor method was an approximate fit too"],
  ], { x: MG, y: 1.5, w: W, colW: [4.0, 4.0, 4.13], fontSize: 13.5, rowH: [0.45, 0.8, 0.8, 0.8, 0.8] });
  card(s, MG, 5.4, W, 1.4, MINT);
  body(s, "FBIL publishes an approximate fit. Forcing a curve through every bond passes small inconsistencies between neighbouring bonds straight into it. Part B therefore fits the same inputs approximately, and puts it through the same six steps.",
    { x: MG + 0.3, y: 5.55, w: W - 0.6, h: 1.1, fontSize: 15 });
  s.addNotes(`FBIL's curve misses its traded inputs by ${f(fr.traded_paise, 1)} paise but its proxy inputs by only ${f(fr.proxy_paise, 1)} paise.`);
}

// ================================================================ PART B: SMOOTHED FIT
partDivider("PART B  ·  TASKS 2 AND 3", "Smoothed fit", ["Method", "Output curves", "Zero curve vs FBIL", "Par curve vs FBIL", "Gap by segment and date", "The long end"]);
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  title(s, "Method: smoothed cubic-spline fit (submitted curve)", "PART B  ·  SMOOTHED FIT  ·  STEP 1");
  card(s, MG, 1.5, 7.3, 2.2, INK);
  s.addText("min  Σ[wᵢ(model priceᵢ − dirty priceᵢ)]² + Σ[√λ(t)·z″(t)]²", { x: MG + 0.3, y: 1.7, w: 6.8, h: 0.5, fontFace: "Consolas", fontSize: 13, color: WHITE, margin: 0, isTextBox: true });
  block(s, [
    "Same inputs and same natural cubic spline as Part A, but 22 fixed knots for 26 bonds, so the curve cannot pass through every price",
    "wᵢ = 1 / (duration × price / 100), so a price error counts like a yield error",
    `λ(t) = ${M.lam} × (1 + ${M.slope} t): a curvature penalty that grows with maturity, where bonds are sparse. T-bill rates are imposed exactly`],
    { x: MG + 0.3, y: 2.2, w: 6.8, h: 1.45, fontSize: 12.5, color: "D8E8EA" });
  card(s, MG, 3.9, 7.3, 2.9, MINT);
  const tu = C.tuning;
  block(s, [{ h: "How λ and the slope were chosen" },
    `A grid of ${tu.n_grid} settings was scored against FBIL's published curve on the four August dates; the lowest August average (${f(tu.august_mean_bp)} bp) was kept.`,
    "11 September was never used in the choice, so it is the only held-out date.",
    "This calibrates two numbers to FBIL. The curve itself is built only from bond prices and T-bill rates.",
    `The held-out result depends on the choice: the ${tu["n_within_0.25bp_of_best"]} settings within 0.25 bp of the best give ${f(tu.test_range_near_best[0])}–${f(tu.test_range_near_best[1])} bp on 11 Sep.`],
    { x: MG + 0.3, y: 4.05, w: 6.8, h: 2.7, fontSize: 13.5 });
  const sh = M.shape;
  card(s, 8.15, 1.5, SW - MG - 8.15, 5.3, PALE);
  block(s, [{ h: "Checks on all five dates" },
    `Still twice differentiable: second-derivative jump ${Number(M.max_d2_jump).toExponential(0)}`,
    `Discount factors fall at every step: ${sh.df_decreasing_all_dates ? "yes" : "no"}`,
    `3-month forward rates ${f(sh.min_fwd_3m, 1)}% to ${f(sh.max_fwd_3m, 1)}%, none negative`,
    `Zero rates ${f(sh.zero_min)}% to ${f(sh.zero_max)}%`,
    { h: "Fit to the input bonds" },
    `Misses its inputs by ${f(M.mean_smooth_price_err_paise, 1)} paise on average; FBIL's curve misses them by ${f(M.mean_fbil_price_err_paise, 1)} paise`],
    { x: 8.4, y: 1.7, w: SW - MG - 8.65, h: 5, fontSize: 14 });
  s.addNotes("Penalising curvature is the standard remedy named by Pienaar and Choudhry, whose spline FBIL uses. Be clear that the two parameters were tuned against FBIL on August data; tune_and_checks.py reproduces the choice.");
}
outputSlide("PART B  ·  SMOOTHED FIT  ·  STEP 2", "Output: zero and par curves from the smoothed fit", "smooth_1_curves.png", SM, READ_CURVES,
  [`Starts at the same T-bill rates and rises to ${f(SM.curve_points["2"].zero_sa)}% at 2 years and ${f(SM.curve_points["10"].zero_sa)}% at 10 years`,
   `Beyond 20 years it climbs steadily to a single peak of ${f(SM.peak[1])}% near ${f(SM.peak[0], 0)} years and eases to ${f(SM.curve_points["50"].zero_sa)}% at 50`,
   "The wobbles of Part A between 25 and 40 years are gone",
   "Zero above par above YTMs at long tenors, as before; the par curve is almost identical to Part A's"]);
chartSlide("PART B  ·  SMOOTHED FIT  ·  STEP 3", "Smoothed fit against FBIL's zero curve", "smooth_2_vs_fbil.png", READ_ZERO("smoothed fit"),
  [`Beyond 14 years the gap averages ${f(SM.mae_gt14)} bp and never exceeds ${f(SM.max_gt14, 1)} bp (exact fit: ${f(EX.mae_gt14)} and ${f(EX.max_gt14, 1)})`,
   `Up to 14 years it is ${f(SM.mae_le14)} bp on average (exact fit: ${f(EX.mae_le14)}). The worst point is ${f(SM.max, 1)} bp at ${SM.max_at} years`,
   `Over all 200 tenors: ${f(SM.mae)} bp; ${f(SM.within_2bp_pct, 0)}% of tenors are within 2 bp (exact fit: ${f(EX.within_2bp_pct, 0)}%)`,
   "The small ripples between 3 and 12 years are FBIL's curve bending around individual bonds, which the smoothed fit does not follow"], null, { fs: 12.5 });
chartSlide("PART B  ·  SMOOTHED FIT  ·  STEP 4", "Smoothed fit: par yield against FBIL", "smooth_3_par.png", READ_PAR("smoothed fit"),
  [`Average par gap ${f(SM.par_mae)} bp (exact fit ${f(EX.par_mae)}); largest ${f(SM.par_max, 1)} bp at ${SM.par_max_at} years`,
   `Beyond 20 years the par gap averages ${f(SM.par_mae_gt20)} bp (exact fit ${f(EX.par_mae_gt20)})`,
   "The 13–20 year dip of Part A is gone",
   "The largest differences have moved to 2–6 years, where the zero curve is also weakest"], null, { fs: 12.5 });
{
  const x = (k) => f(sg(SM, k), 1), pd = (k) => PD.map((d) => d[k]);
  chartSlide("PART B  ·  SMOOTHED FIT  ·  STEP 5", "Smoothed fit: gap to FBIL by segment and by date", "smooth_4_accuracy.png", READ_ACC,
    [`By segment (11 Sep): between ${x("30-40")} and ${x("20-30")} bp in every band beyond 14 years; up to 10 years ${x("5-10")}–${x("1-3")} bp, worst at 1–3 years`,
     `By date: beyond 14 years ${f(Math.min(...pd("smooth_gt14")))}–${f(Math.max(...pd("smooth_gt14")))} bp; up to 14 years ${f(Math.min(...pd("smooth_le14")))}–${f(Math.max(...pd("smooth_le14")))} bp`,
     `5 August is the weak date (${f(PD[0].smooth_mae)} bp). It was the RBI policy day; FBIL's methodology names policy events as a source of volatility`,
     `Five-date average: ${f(M.mean_smooth_le14)} bp up to 14 years, ${f(M.mean_smooth_gt14)} bp beyond (exact fit ${f(M.mean_exact_le14)} and ${f(M.mean_exact_gt14)})`],
    null, { maxH: 4.3, fs: 12.5, takeaway: [{ p: "Compared with Part A the bars are flatter across maturities: the long end improves sharply, and the bands up to 10 years lose 1–2 bp. The 1–3 year band has no input bond between the 1-year T-bill and 2.6 years." }] });
}
chartSlide("PART B  ·  SMOOTHED FIT  ·  STEP 6", "Smoothed fit: the long end", "smooth_5_long_end.png", READ_LONG("smoothed fit"),
  ["The curve follows FBIL's through all three long gaps, with no bulge between 30 and 37.6 years",
   `It peaks at ${f(SM.peak[1])}% near ${f(SM.peak[0], 0)} years, where FBIL's curve also peaks`,
   "The kinks around 27–29 years are gone: the penalty stops the curve bending to fit small differences between neighbouring bonds",
   `Largest gap beyond 14 years: ${f(SM.max_gt14, 1)} bp`],
  null, { maxH: 4.3, fs: 12.5, takeaway: [{ p: "Same chart as Part A, Step 6. Allowing small pricing errors on individual bonds removes both the overshoot in gaps and the noise between close bonds." }] });

// ================================================================ PART C: HEAD TO HEAD
partDivider("PART C  ·  TASK 3", "Exact fit or smoothed fit?", ["Side by side", "Leave-one-out test", "Why both differ from FBIL", "Alternatives tested"]);
{
  const { s, below } = chartSlide("PART C  ·  STEP 1", "Side by side", "12_segments.png",
    ["Chart: grey is the exact fit (Part A), orange the smoothed fit (Part B). Each pair is one maturity band on 11 Sep; bar height is the average gap to FBIL in that band",
     "Table: the same comparison as single numbers, on 11 Sep and averaged over all five dates. Lower is better; bold marks the better curve in each row"],
    ["Up to 10 years the exact fit is closer to FBIL by 1–2 bp",
     "From 10 to 14 years they are level",
     "Beyond 14 years the smoothed fit is closer by 4–12 bp",
     "144 of FBIL's 200 tenors lie beyond 14 years, so all-tenor averages favour the smoothed fit"],
    null, { maxH: 2.95, fs: 12.5 });
  body(s, "Average absolute gap to FBIL's published curve, in basis points (lower is better)",
    { x: MG, y: below - 0.1, w: 7.9, h: 0.3, fontSize: 12, bold: true, color: TEAL });
  tbl(s, [["Curve compared · date · tenors", "Exact fit (Part A)", "Smoothed fit (Part B)"],
    ["Zero curve · 11 Sep (held out) · all 200 tenors", f(o.exact_mae), { t: f(o.smooth_mae), b: true }],
    ["Zero curve · 11 Sep · up to 14 years", { t: f(o.exact_le14), b: true }, f(o.smooth_le14)],
    ["Zero curve · 11 Sep · beyond 14 years", f(o.exact_gt14), { t: f(o.smooth_gt14), b: true }],
    ["Zero curve · average of 5 dates · up to 14 years", { t: f(M.mean_exact_le14), b: true }, f(M.mean_smooth_le14)],
    ["Zero curve · average of 5 dates · beyond 14 years", f(M.mean_exact_gt14), { t: f(M.mean_smooth_gt14), b: true }],
    ["Par curve · average of 5 dates · all 200 tenors", f(M.mean_exact_par_mae), { t: f(M.mean_smooth_par_mae), b: true }]],
    { x: MG, y: below + 0.25, w: 7.9, colW: [4.1, 1.9, 1.9], fontSize: 11, right: [1, 2], rowH: 0.29 });
  body(s, "Bold = the better (smaller) value in each row. Held out: 11 Sep was not used to choose the smoothing settings.",
    { x: MG, y: below + 0.25 + 7 * 0.335 + 0.02, w: 7.9, h: 0.25, fontSize: 10.5, color: MUTED });
}
{
  const L = C.loo;
  chartSlide("PART C  ·  STEP 2", "Leave-one-out test: accuracy without using FBIL's curve", "11_holdout.png",
    ["Each dot is one input bond on one date. The bond was removed, the curve refitted from the other bonds, and the bond priced from that curve",
     "y-axis: model YTM minus the bond's published YTM (bp). The first and last bond on each date are excluded (their removal would need extrapolation)"],
    [`${L.n} hold-outs over five dates. Average miss: smoothed ${f(L.smooth_mae_bp)} bp, exact ${f(L.exact_mae_bp)} bp`,
     `Up to 14 years: ${f(L.smooth_le14)} vs ${f(L.exact_le14)} bp. Beyond: ${f(L.smooth_gt14)} vs ${f(L.exact_gt14)} bp`,
     "The largest exact-fit misses are around 19–20 years, where neighbouring bonds are far apart",
     "Against FBIL the exact fit wins up to 14 years; at predicting a missing bond it does not"],
    null, { fs: 12.5, takeaway: [{ p: "This test needs no benchmark. The smoothed fit predicts better both inside and beyond 14 years, so smoothing improves the curve itself, not just its match to FBIL. We submit the smoothed fit." }] });
}
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  title(s, "Why both curves still differ from FBIL's", "PART C  ·  STEP 3");
  const g = R.gaps_beyond_14;
  tbl(s, [["Factor", "Evidence", "Affects"],
    ["Methodology", `FBIL fits approximately with a smoothing step it does not publish, and selects inputs from trade counts and volumes we cannot see. We use FBIL's flagged inputs; ${R.n_inputs_proxy} of ${R.n_inputs} are FBIL proxy yields, not trades.`, "Both curves"],
    ["Data accuracy", "FBIL rounds zero rates to 2 decimals (±0.5 bp). T-bill rates were copied by hand; the 6M rate is 1 bp below FBIL's curve on 3 dates.", "Both curves, under 1 bp"],
    ["Interpolation", "Changing what is splined or the end condition does not fix the exact fit's long end (next slide). The curvature penalty does.", "Mainly the exact fit"],
    ["Sparse long end", `${R.n_inputs_le14} input bonds lie within 14 years and ${R.n_inputs_gt14} cover the other 36, with gaps of ${g.slice(1).join(", ")} years.`, "Mainly the exact fit"],
    ["Short-end flattening", "No input bond between the 1-year T-bill and 2.6 years; the penalty flattens the curve there.", "Mainly the smoothed fit"]],
    { x: MG, y: 1.5, w: W, colW: [2.2, 7.6, 2.33], fontSize: 13, rowH: [0.45, 0.95, 0.8, 0.8, 0.8, 0.8] });
}
{
  const { s, below } = chartSlide("PART C  ·  STEP 4", "Alternatives tested on the exact fit", "03_variants.png",
    ["Each line is one variant's zero rate minus FBIL's (bp), 11 September",
     "V1 is the exact fit used above. V2 lies almost on top of V1. V6 is off the scale and appears only in the table"],
    ["Dropping the 3M T-bill (V2) is slightly worse up to 14 years, which supports FBIL v6 adding it",
     "Splining the discount factor (V3) or the forward rate (V6) is worse, the forward spline badly so",
     "A not-a-knot end (V4) makes the 50-year end swing by over 70 bp",
     "Our own rule-based bond selection (V5) helps beyond 14 years but hurts the short end: published yields of non-traded bonds include FBIL's liquidity adjustment"],
    null, { maxH: 3.25, fs: 12.5 });
  const rows = [["Variant", "≤14y", ">14y", "Worst"]];
  [["V1", "Exact fit (zero rate, natural)"], ["V2", "Without 3M T-bill"], ["V3", "Spline on −ln DF"], ["V4", "Not-a-knot end"], ["V5", "Own bond selection"], ["V6", "Spline on forward rate"]]
    .forEach(([k, n]) => { const v = V(k); rows.push([`${k} ${n}`, f(v.MAE_le14y_bp), f(v.MAE_gt14y_bp), f(v.max_abs_bp, 1)]); });
  tbl(s, rows, { x: MG, y: below - 0.05, w: 7.9, colW: [4.3, 1.2, 1.2, 1.2], fontSize: 10.5, right: [1, 2, 3], rowH: 0.26 });
}

// ================================================================ TASK 4
section("4", "Bonus: Pricing STRIPS", ["The security and the procedure", "Results and a worked example", "The STRIP values", "Checks and findings"]);
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  title(s, "The security and the procedure", "TASK 4  ·  STEP 1");
  tbl(s, [["07.13 KL SGS 2058 (IN2020250089)", ""],
    ["Maturity", "2 July 2058, 31.8 years from settlement (15 Sep 2026)"],
    ["Why this bond", "The guidelines allow stripping of bonds paying on 2 Jan and 2 Jul. 23 of 5,438 SDLs qualify; this is the longest"],
    ["Discount curve", "Our smoothed G-Sec ZCYC. FBIL's SDL curve ends at 14 years and cannot reach 2058"]],
    { x: MG, y: 1.5, w: 5.4, colW: [1.6, 3.8], fontSize: 12 });
  const st = [
    ["Cash flows", "64 coupon STRIPS of 3.565 per ₹100 of the bond and one principal STRIP of 100. Each is a separate zero-coupon security."],
    ["Present value", "PV = cash flow × DF(t), with t in actual days / 365.25 from settlement and DF from our curve."],
    ["Normalise (para 15.2)", "Factor = min(book, market value) ÷ ΣPV, so the STRIPS add up exactly to the bond and stripping creates no profit or loss."],
    ["Per STRIP", "Price per ₹100 face, implied yield, and the face amount created per ₹1 crore of the bond."]];
  st.forEach((it, i) => {
    const y = 1.5 + i * 1.33;
    card(s, 6.35, y, SW - MG - 6.35, 1.18, i % 2 ? PALE : MINT);
    s.addShape(pres.shapes.OVAL, { x: 6.55, y: y + 0.33, w: 0.5, h: 0.5, fill: { color: TEAL }, line: { color: TEAL } });
    s.addText(String(i + 1), { x: 6.55, y: y + 0.33, w: 0.5, h: 0.5, fontFace: HEAD, fontSize: 17, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0, isTextBox: true });
    body(s, it[0], { x: 7.3, y: y + 0.13, w: 5.3, h: 0.35, fontSize: 15, bold: true, fontFace: HEAD });
    body(s, it[1], { x: 7.3, y: y + 0.5, w: 5.3, h: 0.65, fontSize: 12, color: MUTED });
  });
  s.addNotes("The RBI guidelines name Government of India securities. FBIL's SDL methodology says the SDL curve exists partly to allow SDL stripping, so we apply the guidelines by analogy.");
}
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  title(s, "Results and a worked example", "TASK 4  ·  STEP 2");
  tbl(s, [["Item", "Value"],
    ["Clean price / accrued interest", `${f(SD.clean, 4)} / ${f(SD.accrued, 4)}`],
    ["Dirty price = market value", { t: f(SD.dirty, 4), b: true }],
    ["Sum of PVs on our curve", f(SD.sum_pv_own, 4)],
    ["Normalisation factor", { t: f(SD.factor_own, 5), b: true }],
    ["Sum of normalised values", `${f(SD.sum_norm, 4)} (= dirty price)`],
    ["STRIPS created", "64 coupon + 1 principal"],
    ["Principal STRIP price / yield", `${f(SD.principal_price, 4)} / ${f(SD.principal_yield)}%`],
    ["Principal STRIP share of value", `${f(SD.principal_share_pct, 1)}%`]],
    { x: MG, y: 1.5, w: 6.1, colW: [3.4, 2.7], fontSize: 14, right: [1], rowH: 0.55 });
  const w1 = SD.worked_first;
  card(s, 7.1, 1.5, SW - MG - 7.1, 5.3, MINT);
  body(s, "First coupon STRIP, GS02JAN2027C", { x: 7.35, y: 1.7, w: 5.2, h: 0.4, fontSize: 16, bold: true, fontFace: HEAD });
  const lines = [
    `t          = ${f(w1.t, 4)} years`,
    `zero rate  = ${f(w1.zero_pct, 3)}%  (our curve)`,
    `DF         = (1 + ${f(w1.zero_pct, 3)}/200)^(−2 × ${f(w1.t, 4)})`,
    `           = ${f(w1.df, 5)}`,
    `PV         = 3.565 × ${f(w1.df, 5)} = ${f(w1.pv, 4)}`,
    `normalised = ${f(SD.factor_own, 5)} × ${f(w1.pv, 4)} = ${f(w1.normalised, 4)}`,
    `price      = 100 × ${f(w1.normalised, 4)} / 3.565`,
    `           = ${f(w1.price100, 4)} per ₹100 of STRIP face`];
  s.addText(lines.join("\n"), { x: 7.35, y: 2.25, w: 5.3, h: 3.0, fontFace: "Consolas", fontSize: 13.5, color: INK, margin: 0, isTextBox: true, valign: "top" });
  body(s, "All 65 rows are in strips_sdl2058_pricing.csv. Face created per ₹1 crore of the bond: ₹3,56,500 per coupon STRIP and ₹1 crore for the principal STRIP.",
    { x: 7.35, y: 5.55, w: 5.3, h: 1.1, fontSize: 12, color: MUTED });
}
chartSlide("TASK 4  ·  STEP 3", "The STRIP values", "05_strips_sdl2058.png",
  ["Left: normalised value of each STRIP per ₹100 of the bond. Teal bars: the 64 coupon STRIPS; orange bar: the principal STRIP at 2058",
   "Right: price per ₹100 of STRIP face (navy, left axis) and implied yield (right axis). Orange: yield after the guidelines' normalisation. Teal dashed: an alternative we propose"],
  ["Coupon STRIP values fall from 3.44 to 0.27 as the discount period lengthens. Together they hold 92% of the bond's value; the principal STRIP holds 8.0%",
   `Prices fall from ${f(SD.first_price, 1)} to ${f(SD.principal_price, 2)} per ₹100 face`,
   `The orange yield starts at ${f(SD.first_yield, 1)}%: the factor cuts every STRIP by 2%, which on a 0.3-year STRIP is a large annual rate`,
   `A constant ${f(SD.implied_spread_bp, 1)} bp spread over our curve gives the same total value with a ${f(SD.alt_first_yield, 1)}% short yield. This is our suggestion, not part of the guidelines`],
  null, { maxH: 4.2, fs: 12.5, takeaway: [{ p: "Normalisation makes the 65 STRIPS add up to the bond's price exactly, but it spreads the 2% gap evenly over all of them. Short STRIPS end up with yields no market would quote; a spread over the curve would keep each STRIP consistent with it." }] });
{
  const { s, below } = chartSlide("TASK 4  ·  STEP 4", "Checks and findings", "09_strips_validation_multidate.png",
    ["For each date, FBIL's ~1,595 published GOI STRIPS (6 months or more) are priced as 100 × DF from each curve",
     "Bar height: average price error in paise per ₹100 face. Navy: FBIL's own curve, used as a control"],
    [`FBIL's curve prices its own STRIPS to ${f(VAL.val_fbil_mae_paise, 1)} paise, which confirms the pricing formula`,
     `Our smoothed curve: ${f(VAL.val_smooth_mae_paise, 1)} paise (${f(VAL.val_smooth_yield_bp, 1)} bp in yield). Exact fit: ${f(VAL.val_exact_mae_paise, 1)} paise`,
     "FBIL prices STRIPS from its ZCYC, so this repeats the curve comparison in price terms rather than testing against market trades",
     `Annex 4 of the guidelines reproduced: ΣPV ${f(A4.sum_pv)} (printed 127.87), factor ${f(A4.factor, 4)} (printed 0.9385)`],
    null, { maxH: 3.6, fs: 12.5 });
  tbl(s, [["Discount curve", "Factor", "Principal STRIP"],
    ["Our smoothed G-Sec curve", f(SD.factor_own, 4), f(SD.principal_price, 4)],
    ["FBIL G-Sec curve", f(SD.factor_fbil, 4), f(SD.principal_price_fbil, 4)],
    ["Our exact-fit curve", f(SD.factor_exact, 4), f(SD.principal_price_exact, 4)],
    [`SDL curve, 14y spread (${f(SD.spread14_bp, 0)} bp) carried on`, f(SD.factor_sdl_ext, 4), f(ST.sensitivity[3].principal_strip_price, 4)]],
    { x: MG, y: below - 0.05, w: 7.9, colW: [4.3, 1.8, 1.8], fontSize: 11, right: [1, 2], rowH: 0.3 });
  s.addNotes(`A factor above 1 means the curve values the cash flows below the bond's market price, so its rates are too high for this bond. The bond's own price implies about ${f(SD.implied_spread_bp, 1)} bp over G-Secs, far below the ${f(SD.spread14_bp, 0)} bp SDL spread at 14 years.`);
}

// ================================================================ INTERACTIVE APP
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  title(s, "Interactive app: any FBIL date", "APPLICATION");
  steps(s, [
    ["Install and run", "Python 3.10 or newer, pip install -r requirements.txt, then streamlit run streamlit_app.py in the code folder."],
    ["Enter a date", "Choose \"Enter FBIL data for a new date\", upload the G-Sec valuation file (.xls or .xlsx) and paste FBIL's T-bill rates. The date is read from the file."],
    ["Read the result", "Zero and par curves, gap to FBIL, and STRIPS appear at once, using the same methodology as this project."],
    ["Adjust", "Switch between exact and smoothed fit and move λ and the slope; the curve refits in about 0.2 seconds."],
  ], 1.4, 2.5);
  tbl(s, [["Input for the new date", "Needed?", "What it gives"],
    ["FBIL G-Sec valuation file", "Required", "Input bonds, prices and yields, FBIL's par curve"],
    ["T-bill rates (pasted from FBIL's page)", "Required", "The 7-day, 3M, 6M and 12M short-end knots"],
    ["FBIL ZCYC and STRIPS file", "Optional", "Comparison with FBIL's zero curve: gap metrics, segment and date tabs"],
    ["FBIL SDL valuation file", "Optional", "STRIPS of any SDL; without it, any strippable G-Sec can be stripped"],
    ["Checks before use", "Automatic", "Dates agree across files, enough input bonds, FBIL's prices reproduce from its yields at some settlement date"]],
    { x: MG, y: 4.1, w: W, colW: [3.9, 1.5, 6.73], fontSize: 12.5, rowH: 0.4 });
  s.addNotes("The app calls the same functions as the submitted scripts, so its numbers match the deck: entering the 11 Sep files as a new date gives 6.38 bp for the exact fit and 1.75 bp for the smoothed fit, and STRIPS factor 0.97963 for the 2058 SDL. Without FBIL's ZCYC file the app still gives our curve, par curve and STRIPS, just without the comparison.");
}

// ================================================================ LIMITATIONS
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  title(s, "Limitations and next steps");
  card(s, MG, 1.4, 6.05, 5.4, MINT);
  block(s, [{ h: "Limitations" },
    "FBIL does not publish its spline set-up or smoothing step; we match its behaviour, not its algorithm",
    "Two parameters are tuned to FBIL's curve, and only one date (11 Sep) is held out",
    `The smoothed fit is less accurate than the exact fit up to 10 years (${f(R.smooth_vs_fbil.mae_le10)} vs ${f(R.exact_vs_fbil.mae_le10)} bp on 11 Sep)`,
    "Five dates over six weeks with no change in the policy rate",
    `${R.n_inputs_proxy} of ${R.n_inputs} inputs on 11 Sep are FBIL proxy yields, not trades`,
    "Stripping an SDL applies the RBI guidelines by analogy"],
    { x: MG + 0.28, y: 1.6, w: 5.5, h: 5.05, fontSize: 15 });
  card(s, 6.95, 1.4, SW - MG - 6.95, 5.4, PALE);
  block(s, [{ h: "Next steps" },
    "Choose λ and the slope by the leave-one-out test instead of FBIL's curve, removing the calibration",
    "A lower curvature penalty below 5 years to close the 1–3 year gap",
    "More dates, including a policy-rate change",
    "Trade-level NDS-OM data to reproduce FBIL's input selection",
    { h: "Application" },
    "streamlit run streamlit_app.py opens the interactive app (previous slide), which accepts FBIL data for any date. python app.py reruns the whole project; python app.py --date <date> --sdl <ISIN> runs one stored date end to end and writes an HTML report"],
    { x: 7.2, y: 1.6, w: SW - MG - 7.45, h: 5.05, fontSize: 15 });
}

// ================================================================ SUMMARY
{
  const s = pres.addSlide(); s.background = { color: INK };
  s.addText("Summary", { x: MG, y: 0.45, w: W, h: 0.7, fontFace: HEAD, fontSize: 32, bold: true, color: WHITE, margin: 0, isTextBox: true });
  const items = [
    ["Data", `FBIL files for five dates; settlement, day count, T-bill treatment and par formula each checked against FBIL's own output`],
    ["Exact fit", `Cubic-spline bootstrap through every input, twice differentiable. On 11 Sep: ${f(EX.mae_le14)} bp from FBIL up to 14 years, ${f(EX.mae_gt14)} bp beyond, with overshoots in the long gaps`],
    ["Smoothed fit", `Same inputs with a curvature penalty (submitted). On 11 Sep: ${f(SM.mae_le14)} bp up to 14 years, ${f(SM.mae_gt14)} bp beyond, ${f(o.smooth_mae)} bp overall. Wins the leave-one-out test (${f(C.loo.smooth_mae_bp)} vs ${f(C.loo.exact_mae_bp)} bp)`],
    ["STRIPS", `65 STRIPS of 07.13 KL SGS 2058, factor ${f(SD.factor_own, 5)}; method checked on Annex 4 and FBIL's published STRIPS`],
  ];
  items.forEach((it, i) => {
    const y = 1.45 + i * 1.3;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: MG, y, w: 8.3, h: 1.12, fill: { color: "173B46" }, line: { color: "173B46" }, rectRadius: 0.08 });
    s.addShape(pres.shapes.OVAL, { x: MG + 0.22, y: y + 0.3, w: 0.5, h: 0.5, fill: { color: AMBER }, line: { color: AMBER } });
    s.addText(String(i + 1), { x: MG + 0.22, y: y + 0.3, w: 0.5, h: 0.5, fontFace: HEAD, fontSize: 17, bold: true, color: INK, align: "center", valign: "middle", margin: 0, isTextBox: true });
    body(s, it[0], { x: MG + 0.95, y: y + 0.14, w: 2, h: 0.35, fontSize: 15, bold: true, color: WHITE, fontFace: HEAD });
    body(s, it[1], { x: MG + 0.95, y: y + 0.46, w: 7.15, h: 0.64, fontSize: 12.5, color: "BFDDE1" });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 9.2, y: 1.45, w: SW - MG - 9.2, h: 5.02, fill: { color: "173B46" }, line: { color: "173B46" }, rectRadius: 0.08 });
  body(s, "Reproduce", { x: 9.45, y: 1.65, w: 3, h: 0.4, fontSize: 16, bold: true, color: WHITE, fontFace: HEAD });
  s.addText("cd code\npython app.py\n\npython app.py --date 2026-09-11 \\\n  --sdl IN2020250089", { x: 9.45, y: 2.15, w: 3.3, h: 1.7, fontFace: "Consolas", fontSize: 11.5, color: "9FC3C9", margin: 0, isTextBox: true });
  body(s, "The first command regenerates every table and chart in this deck from the FBIL input files. The second runs one date end to end and writes an HTML report.",
    { x: 9.45, y: 4.05, w: 3.3, h: 2.2, fontSize: 13, color: "BFDDE1" });
}

pres.writeFile({ fileName: path.join(ROOT, "ZCYC_MiniProject_Presentation.pptx") }).then((p) => console.log("wrote", p));
