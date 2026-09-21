"""Bootstrapped cubic-spline zero coupon yield curve (ZCYC).

Method
------
* Curve = natural cubic spline (C2: continuous 1st and 2nd derivative) through knots.
  variant "zero"  : spline on the semi-annual zero rate z(t)
  variant "logdf" : spline on -ln DF(t) (i.e. on the discount function), DF(0)=1 anchor
* Short-end knots are FBIL T-bill rates (fixed): 7-day, 6M, 12M (optionally 3M),
  each treated as a semi-annually compounded zero rate at its tenor.
* Every input coupon bond gets one knot at its maturity. The knot zero rates are the unknowns;
  they are solved simultaneously (Newton-type root finding) so the spline reprices every input
  bond's DIRTY price exactly (dirty = FBIL clean price + accrued, T+1 settlement).
  This is a bootstrap in the sense that each bond's price pins down the zero rate at its maturity,
  with all earlier cash flows discounted on the same curve.
"""
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import root

import conventions as cv


class ZeroCurve:
    def __init__(self, t_knots, z_knots_pct, variant="zero", bc="natural"):
        self.variant = variant
        self.bc = bc
        self.t = np.asarray(t_knots, float)
        self.z = np.asarray(z_knots_pct, float)
        if variant == "zero":
            self._spl = CubicSpline(self.t, self.z, bc_type=bc, extrapolate=True)
        elif variant == "cczero":   # spline on continuously-compounded zero rate
            cc = 200.0 * np.log1p(self.z / 200.0)
            self._spl = CubicSpline(self.t, cc, bc_type=bc, extrapolate=True)
        elif variant == "logdf":
            y = 2.0 * self.t * np.log1p(self.z / 200.0)           # -ln DF at knots
            self._spl = CubicSpline(np.r_[0.0, self.t], np.r_[0.0, y], bc_type=bc, extrapolate=True)
        else:
            raise ValueError(variant)

    def df(self, t):
        t = np.asarray(t, float)
        if self.variant == "zero":
            return cv.df_semiannual(self._spl(t), t)
        if self.variant == "cczero":
            return np.exp(-self._spl(t) / 100.0 * t)
        return np.exp(-self._spl(t))

    def zero(self, t):
        """Semi-annual zero rate, percent."""
        t = np.asarray(t, float)
        if self.variant == "zero":
            return self._spl(t)
        return cv.zero_from_df(self.df(t), t)

    def max_second_derivative_jump(self):
        """Largest jump of the spline's 2nd derivative across interior knots (0 => twice differentiable)."""
        spl = self._spl
        xs = spl.x[1:-1]
        eps = 1e-9
        return float(np.max(np.abs(spl(xs + eps, 2) - spl(xs - eps, 2))))


def tbill_knots(tbills, use_3m=False):
    """Short-end knots (t in years, rate pct). FBIL nominal tenor mapping: 6M->0.5y, 12M->1.0y."""
    r = {row.tenor: row.rate_pct for row in tbills.itertuples()}
    pts = [(7.0 / cv.DAYS_PER_YEAR, r["7 Days"])]
    if use_3m:
        pts.append((0.25, r["3 Months"]))
    pts += [(0.5, r["6 Months"]), (1.0, r["12 Months"])]
    return pts


def bootstrap(bonds, tbills, variant="zero", use_3m=False, settle=cv.SETTLEMENT_DATE, bc="natural"):
    """Fit the curve to `bonds` (DataFrame: coupon, maturity, price(clean), ytm) + T-bill knots."""
    bonds = bonds.sort_values("maturity").reset_index(drop=True)
    tb = tbill_knots(tbills, use_3m)
    tb_t = np.array([p[0] for p in tb])
    tb_z = np.array([p[1] for p in tb])

    bond_t = np.array([cv.yearfrac(m, settle) for m in bonds["maturity"]])
    order_ok = np.all(np.diff(np.r_[tb_t, bond_t]) > 0)
    if not order_ok:
        raise ValueError("Knot maturities must be strictly increasing and beyond the T-bill knots")

    flows = []   # per bond: (t_j array, cf array)
    target = []  # dirty price
    for r in bonds.itertuples():
        cfs = cv.cash_flows(r.coupon, r.maturity, settle)
        flows.append((np.array([cv.yearfrac(d, settle) for d, _ in cfs]), np.array([a for _, a in cfs])))
        target.append(r.price + cv.accrued_interest(r.coupon, r.maturity, settle))
    target = np.array(target)

    t_all = np.r_[tb_t, bond_t]

    def model_prices(x):
        curve = ZeroCurve(t_all, np.r_[tb_z, x], variant, bc)
        return np.array([np.dot(cf, curve.df(tj)) for tj, cf in flows])

    x0 = bonds["ytm"].to_numpy(float)
    sol = root(lambda x: model_prices(x) - target, x0, method="hybr", tol=1e-13)
    if not sol.success:
        sol = root(lambda x: model_prices(x) - target, x0, method="lm", tol=1e-13)
    curve = ZeroCurve(t_all, np.r_[tb_z, sol.x], variant, bc)
    err = model_prices(sol.x) - target
    info = {"converged": bool(sol.success), "max_abs_price_error": float(np.max(np.abs(err))),
            "n_bonds": len(bonds), "n_knots": len(t_all), "bond_t": bond_t}
    return curve, info


def par_yield(curve, tenors):
    """Par yield (semi-annual, percent) from the curve.

    Reverse-engineered from FBIL's par sheet: coupons c/2 at T, T-0.5, ... (>0); the earliest
    coupon is pro-rated when it falls at a quarter (stub) date. Reproduces FBIL's par yields from
    FBIL's own zero curve to <1 bp (2-decimal rounding)."""
    out = []
    for T in np.atleast_1d(tenors):
        ds, t = [], float(T)
        while t > 1e-9:
            ds.append(round(t, 6))
            t -= 0.5
        ds = np.array(sorted(ds))
        frac = np.ones(len(ds))
        frac[0] = min(1.0, ds[0] / 0.5)
        annuity = np.sum(frac * curve.df(ds))
        out.append(200.0 * (1.0 - float(curve.df(T))) / annuity)
    return np.array(out)


# ---------------------------------------------------------------------------------------------
# Variant: natural cubic spline on the INSTANTANEOUS FORWARD rate f(t)  (smooth-forward-curve idea)
# DF(t) = exp(-int_0^t f).  Unknowns: f at every knot (T-bill knots too); equations: the T-bill
# zero rates and the input bond prices.
# ---------------------------------------------------------------------------------------------
class ForwardCurve:
    def __init__(self, t_knots, f_knots_pct):
        self.t = np.asarray(t_knots, float)
        self.f = np.asarray(f_knots_pct, float)
        self._spl = CubicSpline(self.t, self.f / 100.0, bc_type="natural", extrapolate=True)
        self._anti = self._spl.antiderivative()
        self._F0 = float(self._anti(0.0))

    def df(self, t):
        t = np.asarray(t, float)
        return np.exp(-(self._anti(t) - self._F0))

    def zero(self, t):
        t = np.asarray(t, float)
        return cv.zero_from_df(self.df(t), t)

    def max_second_derivative_jump(self):
        xs = self._spl.x[1:-1]
        eps = 1e-9
        return float(np.max(np.abs(self._spl(xs + eps, 2) - self._spl(xs - eps, 2))))


def bootstrap_forward(bonds, tbills, use_3m=False, settle=cv.SETTLEMENT_DATE):
    bonds = bonds.sort_values("maturity").reset_index(drop=True)
    tb = tbill_knots(tbills, use_3m)
    tb_t = np.array([p[0] for p in tb]); tb_z = np.array([p[1] for p in tb])
    tb_df = cv.df_semiannual(tb_z, tb_t)
    bond_t = np.array([cv.yearfrac(m, settle) for m in bonds["maturity"]])
    t_all = np.r_[tb_t, bond_t]
    flows, target = [], []
    for r in bonds.itertuples():
        cfs = cv.cash_flows(r.coupon, r.maturity, settle)
        flows.append((np.array([cv.yearfrac(d, settle) for d, _ in cfs]), np.array([a for _, a in cfs])))
        target.append(r.price + cv.accrued_interest(r.coupon, r.maturity, settle))
    target = np.array(target)

    def resid(f):
        c = ForwardCurve(t_all, f)
        e1 = np.log(c.df(tb_t)) - np.log(tb_df)                       # T-bill zero constraints
        e2 = np.array([np.dot(cf, c.df(tj)) for tj, cf in flows]) - target
        return np.r_[e1 * 100.0, e2]

    f0 = np.r_[tb_z, bonds["ytm"].to_numpy(float)]
    sol = root(resid, f0, method="hybr", tol=1e-13)
    c = ForwardCurve(t_all, sol.x)
    r = resid(sol.x)
    return c, {"converged": bool(sol.success), "max_abs_price_error": float(np.max(np.abs(r[len(tb_t):]))),
               "max_abs_tbill_error": float(np.max(np.abs(r[:len(tb_t)]))), "n_bonds": len(bonds),
               "n_knots": len(t_all), "bond_t": bond_t}


def select_inputs_rule(gsec_fixed, min_gap_years=0.25):
    """Own input selection built from the documented rules (no trade data available):
       * >1y and <=14y: nearest bond to each half-year target (1.5, 2.0, ... 14.0) within +/-0.25y,
         keeping adjacent inputs at least 90 days (0.25y) apart;
       * >14y: one bond per 4-year bucket (14-18, 18-22, 22-26, 26-30, 30-34, >34), nearest to the
         bucket mid-point, plus the longest outstanding bond as compulsory last point."""
    g = gsec_fixed.copy()
    g["t"] = [cv.yearfrac(m) for m in g["maturity"]]
    g = g[g["t"] > 1.0].sort_values("t")
    chosen = []
    for target in np.arange(1.5, 14.01, 0.5):
        w = g[(g["t"] > target - 0.25) & (g["t"] <= target + 0.25)]
        if len(w):
            chosen.append(w.iloc[(w["t"] - target).abs().argmin()]["isin"])
    for lo, hi in [(14, 18), (18, 22), (22, 26), (26, 30), (30, 34), (34, 60)]:
        w = g[(g["t"] > lo) & (g["t"] <= hi)]
        if len(w):
            mid = (lo + hi) / 2 if hi < 60 else 40.0
            chosen.append(w.iloc[(w["t"] - mid).abs().argmin()]["isin"])
    chosen.append(g.iloc[-1]["isin"])
    sel = g[g["isin"].isin(chosen)].sort_values("t")
    keep, last_t = [], -9
    for r in sel.itertuples():
        if r.t - last_t >= min_gap_years:
            keep.append(r.isin); last_t = r.t
    return sel[sel["isin"].isin(keep)].drop(columns="t").sort_values("maturity")
