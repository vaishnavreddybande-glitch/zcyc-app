"""Date-parameterised ZCYC engine: exact-fit splines and penalised (smoothed) fits.

All curves are built ONLY from input-bond prices and FBIL T-bill rates.
FBIL's published ZCYC is never an input - it is used solely to score accuracy.
"""
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import root, least_squares

import multidate as md

DPY = md.DAYS_PER_YEAR


def df_semi(z_pct, t):
    return (1.0 + np.asarray(z_pct) / 200.0) ** (-2.0 * np.asarray(t))


def zero_from_df(d, t):
    return 200.0 * (np.asarray(d) ** (-1.0 / (2.0 * np.asarray(t))) - 1.0)


def semi_to_annual(z):
    return 100.0 * ((1.0 + np.asarray(z) / 200.0) ** 2 - 1.0)


# ----------------------------------------------------------------- T-bill knots
def tbill_knots(tb, use_3m=True, use_7d=True, bey=False):
    """FBIL money-market inputs. v6 uses overnight(7-day), 3M, 6M and 12M.

    bey=True converts the published money-market rate (simple interest, act/365)
    to a semi-annually compounded bond-equivalent zero rate, as the methodology's
    'bond equivalent market YTMs' wording implies."""
    r = {row.tenor: row.rate_pct for row in tb.itertuples()}
    pts = []
    if use_7d:
        pts.append((7.0 / DPY, r["7 Days"]))
    if use_3m:
        pts.append((0.25, r["3 Months"]))
    pts += [(0.5, r["6 Months"]), (1.0, r["12 Months"])]
    if bey:
        out = []
        for t, y in pts:
            days = round(t * 365)
            dfac = 1.0 / (1.0 + y / 100.0 * days / 365.0)   # money-market discount factor
            out.append((t, float(zero_from_df(dfac, t))))
        pts = out
    return pts


# ----------------------------------------------------------------- curve objects
class SplineCurve:
    """Natural cubic spline on the semi-annual zero rate through (t, z) knots."""

    def __init__(self, t, z, bc="natural"):
        self.t = np.asarray(t, float)
        self.z = np.asarray(z, float)
        self._s = CubicSpline(self.t, self.z, bc_type=bc, extrapolate=True)

    def zero(self, x):
        return self._s(np.asarray(x, float))

    def df(self, x):
        x = np.asarray(x, float)
        return df_semi(self._s(x), x)

    def d2_jump(self):
        xs = self._s.x[1:-1]
        e = 1e-9
        return float(np.max(np.abs(self._s(xs + e, 2) - self._s(xs - e, 2)))) if len(xs) else 0.0


class ForwardSplineCurve:
    """Cubic spline on the instantaneous forward rate f(t); DF = exp(-int f)."""

    def __init__(self, t, f_pct, bc="natural"):
        self.t = np.asarray(t, float)
        self._s = CubicSpline(self.t, np.asarray(f_pct, float) / 100.0, bc_type=bc, extrapolate=True)
        self._a = self._s.antiderivative()
        self._a0 = float(self._a(0.0))

    def df(self, x):
        x = np.asarray(x, float)
        return np.exp(-(self._a(x) - self._a0))

    def zero(self, x):
        x = np.asarray(x, float)
        return zero_from_df(self.df(x), x)

    def fwd(self, x):
        return 100.0 * self._s(np.asarray(x, float))

    def d2_jump(self):
        xs = self._s.x[1:-1]
        e = 1e-9
        return float(np.max(np.abs(self._s(xs + e, 2) - self._s(xs - e, 2)))) if len(xs) else 0.0


# ----------------------------------------------------------------- bond helpers
def bond_flows(bonds, settle):
    out, tgt = [], []
    for r in bonds.itertuples():
        cfs = md.cash_flows(r.coupon, r.maturity, settle)
        out.append((np.array([md.yearfrac(d, settle) for d, _ in cfs]), np.array([a for _, a in cfs])))
        tgt.append(r.price + md.accrued(r.coupon, r.maturity, settle))
    return out, np.array(tgt)


def duration(tj, cf, curve):
    d = curve.df(tj)
    p = float(np.dot(cf, d))
    return float(np.dot(tj * cf, d) / p), p


# ----------------------------------------------------------------- exact-fit bootstrap
def bootstrap(bonds, tb, settle, use_3m=True, bc="natural", bey=False, variable="zero"):
    bonds = bonds.sort_values("maturity").reset_index(drop=True)
    knots = tbill_knots(tb, use_3m=use_3m, bey=bey)
    kt = np.array([p[0] for p in knots], float)
    kz = np.array([p[1] for p in knots], float)
    bt = np.array([md.yearfrac(m, settle) for m in bonds["maturity"]], float)
    t_all = np.r_[kt, bt]
    if np.any(np.diff(t_all) <= 0):
        raise ValueError("knots not strictly increasing")
    flows, target = bond_flows(bonds, settle)

    def build(x):
        return SplineCurve(t_all, np.r_[kz, x], bc)

    def resid(x):
        c = build(x)
        return np.array([np.dot(cf, c.df(tj)) for tj, cf in flows]) - target

    x0 = bonds["ytm"].to_numpy(float)
    sol = root(resid, x0, method="hybr", tol=1e-13)
    if not sol.success:
        sol = root(resid, x0, method="lm", tol=1e-13)
    c = build(sol.x)
    return c, {"max_price_err": float(np.max(np.abs(resid(sol.x)))), "converged": bool(sol.success),
               "n_bonds": len(bonds), "bond_t": bt, "knot_t": t_all}


# ----------------------------------------------------------------- penalised (smoothed) forward fit
def penalised_forward(bonds, tb, settle, lam0=1.0, lam_slope=0.0, knot_step=1.0, t_max=None,
                      use_3m=True, bey=False, weight="duration", t_pen=0.0, fine_below=None,
                      fine_step=0.25):
    """Fit a forward-rate spline minimising weighted price error + roughness penalty.

    penalty_k = sqrt(lambda(t_k)) * f''(t_k),  lambda(t) = lam0 * (1 + lam_slope * t)
    T-bill zero rates are imposed as hard-weighted residuals (weight 1e3).
    """
    bonds = bonds.sort_values("maturity").reset_index(drop=True)
    knots = tbill_knots(tb, use_3m=use_3m, bey=bey)
    kt = np.array([p[0] for p in knots], float)
    kz = np.array([p[1] for p in knots], float)
    kdf = df_semi(kz, kt)
    flows, target = bond_flows(bonds, settle)
    bt = np.array([md.yearfrac(m, settle) for m in bonds["maturity"]], float)
    t_max = t_max or float(bt.max())

    dense = np.arange(0.25, (fine_below or 0.0) + 1e-9, fine_step) if fine_below else np.array([])
    coarse_start = max(0.5, (fine_below or 0.0) + knot_step)
    grid = np.unique(np.r_[0.0, kt, dense, np.arange(coarse_start, t_max + knot_step, knot_step), t_max])
    fine = np.linspace(0.05, t_max, 400)
    lam = lam0 * (1.0 + lam_slope * np.maximum(fine - t_pen, 0.0))
    lam = np.where(fine < t_pen, 0.0, lam)

    # weights ~ 1/(duration*price) so a price residual behaves like a yield residual
    c0, _ = bootstrap(bonds, tb, settle, use_3m=use_3m, bey=bey)
    if weight == "duration":
        w = np.array([1.0 / (duration(tj, cf, c0)[0] * duration(tj, cf, c0)[1] / 100.0) for tj, cf in flows])
    else:
        w = np.ones(len(flows))

    def resid(theta):
        c = ForwardSplineCurve(grid, theta)
        px = np.array([np.dot(cf, c.df(tj)) for tj, cf in flows]) - target
        tb_e = (np.log(c.df(kt)) - np.log(kdf)) * 1e3
        pen = np.sqrt(lam) * c._s(fine, 2) * 100.0
        return np.r_[px * w, tb_e, pen]

    theta0 = np.interp(grid, np.r_[kt, bt], np.r_[kz, bonds["ytm"].to_numpy(float)])
    sol = least_squares(resid, theta0, method="lm", xtol=1e-12, ftol=1e-12, max_nfev=20000)
    c = ForwardSplineCurve(grid, sol.x)
    px = np.array([np.dot(cf, c.df(tj)) for tj, cf in flows]) - target
    return c, {"max_price_err": float(np.max(np.abs(px))), "mean_abs_price_err": float(np.abs(px).mean()),
               "n_bonds": len(bonds), "bond_t": bt, "converged": bool(sol.success)}


# ----------------------------------------------------------------- scoring against FBIL
def score(curve, zcyc, t_lo=0.25, t_hi=None):
    g = zcyc["tenor"].to_numpy(float)
    f = zcyc["zero_semi"].to_numpy(float)
    m = (g >= t_lo) & (g <= (t_hi if t_hi else g.max()))
    d = (curve.zero(g[m]) - f[m]) * 100.0
    lo = g[m] <= 14
    return {"mae": float(np.abs(d).mean()), "rmse": float(np.sqrt((d ** 2).mean())),
            "max": float(np.abs(d).max()), "max_at": float(g[m][np.abs(d).argmax()]),
            "mae_le14": float(np.abs(d[lo]).mean()), "mae_gt14": float(np.abs(d[~lo]).mean()),
            "bias": float(d.mean()), "diff": d, "grid": g[m]}


def par_yield(curve, tenors):
    out = []
    for T in np.atleast_1d(tenors):
        ds, t = [], float(T)
        while t > 1e-9:
            ds.append(round(t, 6))
            t -= 0.5
        ds = np.array(sorted(ds))
        fr = np.ones(len(ds))
        fr[0] = min(1.0, ds[0] / 0.5)
        out.append(200.0 * (1.0 - float(curve.df(T))) / float(np.sum(fr * curve.df(ds))))
    return np.array(out)


# ----------------------------------------------------------------- least-squares fit on a fixed knot grid
DEFAULT_KNOTS = [1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.5, 10.0, 12.0, 14.0, 17.0, 20.0, 24.0, 28.0, 33.0, 40.0, 50.0]


def ls_fit(bonds, tb, settle, knots=None, lam=0.0, use_3m=True, bey=False, weight="duration",
           bc="natural", t_pen=0.0, lam_slope=0.0):
    """Weighted least-squares cubic spline on the zero rate over a FIXED knot grid.

    Unlike the exact-fit bootstrap this does NOT force every bond to reprice exactly; it is the
    approximating fit that FBIL's published curve appears to use (its own curve misprices its own
    inputs by ~8 paise). Fewer knots than bonds = smoothing by construction.
    T-bill zero rates are imposed as heavily-weighted residuals.
    """
    bonds = bonds.sort_values("maturity").reset_index(drop=True)
    tbk = tbill_knots(tb, use_3m=use_3m, bey=bey)
    kt = np.array([p[0] for p in tbk], float)
    kz = np.array([p[1] for p in tbk], float)
    flows, target = bond_flows(bonds, settle)
    bt = np.array([md.yearfrac(m, settle) for m in bonds["maturity"]], float)

    ks = np.array(knots if knots is not None else DEFAULT_KNOTS, float)
    ks = ks[(ks > kt[-1] + 0.05) & (ks <= bt.max() + 6.0)]
    ks = np.r_[ks, bt.max()] if bt.max() > ks[-1] + 0.05 else ks
    grid = np.r_[kt, np.unique(ks)]

    c0, _ = bootstrap(bonds, tb, settle, use_3m=use_3m, bey=bey)
    if weight == "duration":
        w = np.array([1.0 / (duration(tj, cf, c0)[0] * duration(tj, cf, c0)[1] / 100.0) for tj, cf in flows])
    elif weight == "equal":
        w = np.ones(len(flows))
    else:
        w = np.array([1.0 / duration(tj, cf, c0)[0] for tj, cf in flows])

    fine = np.linspace(kt[-1], bt.max(), 300)
    lam_t = max(lam, 0.0) * (1.0 + lam_slope * np.maximum(fine - t_pen, 0.0))
    pen_w = np.where(fine >= t_pen, np.sqrt(lam_t), 0.0)

    def build(x):
        return SplineCurve(grid, np.r_[kz, x], bc)

    def resid(x):
        c = build(x)
        px = (np.array([np.dot(cf, c.df(tj)) for tj, cf in flows]) - target) * w
        if lam > 0:
            return np.r_[px, pen_w * c._s(fine, 2)]
        return px

    x0 = np.interp(grid[len(kt):], np.r_[kt, bt], np.r_[kz, bonds["ytm"].to_numpy(float)])
    sol = least_squares(resid, x0, method="lm", xtol=1e-13, ftol=1e-13, max_nfev=40000)
    c = build(sol.x)
    px = np.array([np.dot(cf, c.df(tj)) for tj, cf in flows]) - target
    return c, {"mean_abs_price_err": float(np.abs(px).mean()), "max_price_err": float(np.abs(px).max()),
               "n_knots": len(grid), "n_bonds": len(bonds), "bond_t": bt, "grid": grid,
               "converged": bool(sol.success), "price_err": px}
