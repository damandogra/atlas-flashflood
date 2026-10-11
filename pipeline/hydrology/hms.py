"""HEC-HMS-equivalent event hydrology for the Ounila basin model.

Same methods as an HEC-HMS basin model, so results can be cross-checked against real HEC-HMS:
  loss       SCS Curve Number (Ia = 0.2 S), optional AMC I / III conversion (Chow et al. 1988)
  transform  Clark unit hydrograph: HEC-HMS synthetic time-area curve + linear reservoir
  routing    variable-parameter Muskingum-Cunge, wide rectangular channel (Ponce & Yevjevich 1978)
  baseflow   none (ephemeral wadi; event peaks are dominated by direct runoff)

Units: area km2, length m, time step seconds, rainfall mm, discharge m3/s.
"""

import json
from dataclasses import dataclass, field

import numpy as np
from numba import njit

from pipeline import config

DT_S = 300                     # computation step, 5 min
SIM_HOURS = 48
CHANNEL_N = 0.045              # gravel-cobble wadi bed (same as the 2D model's channel cells)
WIDTH_COEF = 3.0               # bankfull width W = WIDTH_COEF * A_km2 ** 0.5 (m)  -- ASSUMPTION
R_OVER_TC = 1.0                # Clark storage coefficient R = R_OVER_TC * Tc. Russell et al. (1979)
                               # give R/Tc 1.5-2.8 for natural basins; 1.0 is the conservative end.
                               # Checked against regional flood evidence (docs/hydrology.md).
TC_FORMULAS = ("giandotti", "temez")   # Kirpich is reported but not used: it was fitted on 1-45 ha
                                       # Tennessee farm basins and underestimates Tc for mountain basins


@dataclass
class Subbasin:
    id: int
    name: str
    kind: str
    area_km2: float
    drainage_km2: float
    cn: float
    tc_h: float
    r_h: float
    downstream: int
    tc_formulas_h: dict = field(default_factory=dict)
    reach: dict | None = None      # {"length_m", "slope", "width_m", "n"} to the downstream point


# --- parameters ---------------------------------------------------------------------

def tc_formulas(sb):
    """Time of concentration (h) by three formulas widely used for Moroccan mountain basins."""
    A = sb["area_km2"]
    L_km = max(sb["longest_flowpath_m"], 30.0) / 1000.0
    S = max(sb["relief_m"] / (L_km * 1000.0), 1e-3)                 # mean slope of the longest path
    dH = max(sb["mean_elev_m"] - sb["outlet_elev_m"], 1.0)
    return {
        "kirpich": 0.0195 * (L_km * 1000.0) ** 0.77 * S ** -0.385 / 60.0,
        "giandotti": (4.0 * np.sqrt(A) + 1.5 * L_km) / (0.8 * np.sqrt(dH)),
        "temez": 0.3 * (L_km / S ** 0.25) ** 0.76,
    }


def load_basin(r_over_tc=R_OVER_TC, width_coef=WIDTH_COEF):
    model = json.loads((config.INTERIM / "basin_model.json").read_text(encoding="utf8"))
    out = []
    for sb in model["subbasins"]:
        tcs = tc_formulas(sb)
        tc = float(np.mean([tcs[k] for k in TC_FORMULAS]))
        tc = max(tc, 0.25)                                    # floor at 15 min
        reach = None
        if sb["reach"]:
            reach = {"length_m": sb["reach"]["length_m"], "slope": sb["reach"]["slope"],
                     "width_m": width_coef * np.sqrt(sb["drainage_km2"]), "n": CHANNEL_N}
        out.append(Subbasin(id=sb["id"], name=sb["name"], kind=sb["kind"], area_km2=sb["area_km2"],
                            drainage_km2=sb["drainage_km2"], cn=sb["cn_amc2"], tc_h=tc, r_h=r_over_tc * tc,
                            downstream=sb["reach"]["to"] if sb["reach"] else 0,
                            tc_formulas_h={k: round(v, 3) for k, v in tcs.items()}, reach=reach))
    return sorted(out, key=lambda s: s.drainage_km2)          # upstream first


def cn_amc(cn2, amc):
    """Convert an AMC II curve number to AMC I (dry) or III (wet) (Chow, Maidment & Mays 1988)."""
    if amc == 1:
        return 4.2 * cn2 / (10.0 - 0.058 * cn2)
    if amc == 3:
        return 23.0 * cn2 / (10.0 + 0.13 * cn2)
    return cn2


# --- loss ------------------------------------------------------------------------------

def scs_excess(p_inc, cn):
    """Incremental excess (mm) from incremental rainfall (mm), SCS CN with Ia = 0.2 S."""
    s = 25400.0 / cn - 254.0
    ia = 0.2 * s
    p = np.cumsum(p_inc)
    pe = np.where(p > ia, (p - ia) ** 2 / (p - ia + s), 0.0)
    return np.diff(np.concatenate([[0.0], pe]))


# --- transform ---------------------------------------------------------------------------

def clark_uh(area_km2, tc_h, r_h, dt_s=DT_S):
    """Clark UH ordinates (m3/s per mm of excess in one step), HEC-HMS synthetic time-area curve."""
    tc_s, r_s = tc_h * 3600.0, max(r_h * 3600.0, dt_s)
    n_ta = max(int(np.ceil(tc_s / dt_s)), 1)
    t = np.arange(1, n_ta + 1) * dt_s / tc_s
    t = np.minimum(t, 1.0)
    cum = np.where(t <= 0.5, 1.414 * t ** 1.5, 1.0 - 1.414 * (1.0 - t) ** 1.5)
    cum[-1] = 1.0
    d_area = np.diff(np.concatenate([[0.0], cum])) * area_km2 * 1e6      # m2 contributing per step
    inflow = d_area * 1e-3 / dt_s                                          # m3/s from 1 mm excess
    ca = dt_s / (r_s + 0.5 * dt_s)
    n = n_ta + int(10 * r_s / dt_s) + 1                                    # until the recession is ~0
    uh = np.zeros(n)
    o = 0.0
    for i in range(n):
        o = ca * (inflow[i] if i < n_ta else 0.0) + (1.0 - ca) * o
        uh[i] = o
    return uh


def subbasin_hydrograph(p_inc, sb, amc=2, n_steps=None):
    excess = scs_excess(p_inc, cn_amc(sb.cn, amc))
    q = np.convolve(excess, clark_uh(sb.area_km2, sb.tc_h, sb.r_h))
    n_steps = n_steps or len(p_inc)
    return q[:n_steps], excess


# --- routing ----------------------------------------------------------------------------

@njit(cache=True)
def _muskingum_cunge(inflow, length, slope, width, n_manning, dt, n_sub):
    """Variable-parameter Muskingum-Cunge through n_sub equal sub-reaches, wide rectangular channel."""
    dx = length / n_sub
    q = inflow.copy()
    for _ in range(n_sub):
        out = np.zeros_like(q)
        out[0] = q[0]
        for t in range(1, len(q)):
            qref = max((q[t - 1] + q[t] + out[t - 1]) / 3.0, 1e-3)
            y = (qref * n_manning / (width * np.sqrt(slope))) ** 0.6
            v = qref / (width * y)
            c = 5.0 / 3.0 * v
            k = dx / c
            x = 0.5 * (1.0 - qref / (width * slope * c * dx))
            x = min(max(x, 0.0), 0.5)
            den = 2.0 * k * (1.0 - x) + dt
            c0 = (dt - 2.0 * k * x) / den
            c1 = (dt + 2.0 * k * x) / den
            c2 = (2.0 * k * (1.0 - x) - dt) / den
            out[t] = max(c0 * q[t] + c1 * q[t - 1] + c2 * out[t - 1], 0.0)
        q = out
    return q


def route(inflow, reach, dt_s=DT_S):
    peak = max(float(inflow.max()), 1e-3)
    y = (peak * reach["n"] / (reach["width_m"] * np.sqrt(reach["slope"]))) ** 0.6
    c = 5.0 / 3.0 * peak / (reach["width_m"] * y)
    n_sub = max(int(np.ceil(reach["length_m"] / (c * dt_s))), 1)     # Courant ~1 at the peak
    return _muskingum_cunge(inflow.astype(np.float64), reach["length_m"], reach["slope"],
                            reach["width_m"], reach["n"], float(dt_s), n_sub)


# --- network ------------------------------------------------------------------------------

def run_network(basin, rain_for, amc=2, dt_s=DT_S):
    """Run the whole basin. rain_for(sb) -> incremental rainfall (mm) per step for that sub-basin.
    Returns {id: {"local", "total", "excess_mm", "rain_mm"}} with totals at each control point."""
    n = len(rain_for(basin[0]))
    res = {}
    for sb in basin:                                         # upstream first
        p = rain_for(sb)
        local, excess = subbasin_hydrograph(p, sb, amc, n)
        total = local.copy()
        for up in basin:
            if up.downstream == sb.id:
                total += route(res[up.id]["total"], up.reach, dt_s)[:n]
        res[sb.id] = {"local": local, "total": total, "excess_mm": float(excess.sum()), "rain_mm": float(p.sum())}
    return res


def summarize(res, basin, dt_s=DT_S):
    rows = {}
    for sb in basin:
        q = res[sb.id]["total"]
        rows[sb.id] = {"name": sb.name, "kind": sb.kind, "drainage_km2": round(sb.drainage_km2, 1),
                       "peak_m3s": round(float(q.max()), 1),
                       "time_to_peak_h": round(float(np.argmax(q) * dt_s / 3600.0), 2),
                       "volume_hm3": round(float(q.sum() * dt_s / 1e6), 3),
                       "specific_m3s_km2": round(float(q.max() / sb.drainage_km2), 2),
                       "local_rain_mm": round(res[sb.id]["rain_mm"], 1),
                       "local_excess_mm": round(res[sb.id]["excess_mm"], 1)}
    return rows
