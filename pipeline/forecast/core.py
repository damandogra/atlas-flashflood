"""Forecast/replay assessment: hourly areal rain -> library flood scenario -> impacts and alert level.

The scenario library was computed for design storms (AMC II, IMERG storm shape) indexed by their
catchment 24 h depth. A forecast is matched to it by:
  1. its largest 24 h total (liquid, areal, x the same areal correction as the design rainfall);
  2. an AMC-equivalent depth: the AMC II depth giving the same SCS runoff over the 21 sub-basins as the
     forecast depth under its actual antecedent moisture (5-day rain, NEH-4 limits);
  3. the library time axis aligned so the design burst (t = 12 h) sits on the forecast's peak hour.
NWP hourly rain is as flat as ERA5 at sub-daily scale (Phase 1), so the library's IMERG-shaped burst is
used for intensities, and the NWP series only for totals and timing.

Context (library depths, sub-basin areas/CNs, correction) comes either from the pipeline outputs
(default, lazy) or from the published web/public/data/meta.json (`use_meta`), so the 6-hourly
GitHub Actions job needs only numpy, pandas and requests.
"""

import json

import numpy as np
import pandas as pd

DESIGN_BURST_H = 12.0
AMC_LIMITS_MM = (12.7, 27.9)
ALERT_RULES = {        # impact-based: ensemble probability of reaching a library flood, or the best guess
    "red": {"scenario": "T50", "prob": 0.3, "deterministic": "T25"},
    "orange": {"scenario": "T10", "prob": 0.3, "deterministic": "T5"},
    "yellow": {"scenario": "T2", "prob": 0.3, "deterministic": "P25"},
}
_CTX = {}


def use_meta(path):
    meta = json.loads(open(path, encoding="utf8").read())
    _CTX.update(library={e["name"]: e["p24_mm"] for e in meta["library"]},
                subbasins=[(s["area_km2"], s["cn"]) for s in meta["subbasins"]],
                correction=meta["correction_factor"],
                rain_points=[(p["lon"], p["lat"], p["w"]) for p in meta["rain_points"]])


def _ctx(key):
    if key not in _CTX:                                   # pipeline defaults (heavy imports, lazy)
        from pipeline import config
        from pipeline.hydraulics.scenarios import library
        from pipeline.hydrology import hms
        idf = json.loads((config.INTERIM / "rainfall" / "idf.json").read_text(encoding="utf8"))
        _CTX.setdefault("library", library())
        _CTX.setdefault("subbasins", [(s.area_km2, s.cn) for s in hms.load_basin()])
        _CTX.setdefault("correction", idf["correction_levels"]["central"])
    return _CTX[key]


def correction():
    return _ctx("correction")


def lib():
    return _ctx("library")


def cn_amc(cn2, amc):
    """AMC II curve number -> AMC I (dry) / III (wet), Chow, Maidment & Mays (1988)."""
    if amc == 1:
        return 4.2 * cn2 / (10.0 - 0.058 * cn2)
    if amc == 3:
        return 23.0 * cn2 / (10.0 + 0.13 * cn2)
    return cn2


def amc_class(antecedent_mm):
    return 1 if antecedent_mm < AMC_LIMITS_MM[0] else (3 if antecedent_mm > AMC_LIMITS_MM[1] else 2)


def basin_runoff(p_mm, amc):
    sb = np.array(_ctx("subbasins"), dtype=float)
    a = sb[:, 0]
    cn = np.array([cn_amc(c, amc) for c in sb[:, 1]])
    s = 25400.0 / cn - 254.0
    q = np.where(p_mm > 0.2 * s, (p_mm - 0.2 * s) ** 2 / (p_mm + 0.8 * s), 0.0)
    return float((q * a).sum() / a.sum())


def amc_equivalent_depth(p24, amc):
    if amc == 2 or p24 <= 0:
        return float(p24)
    target = basin_runoff(p24, amc)
    if target <= 0:
        return 0.0
    lo, hi = 0.0, 400.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if basin_runoff(mid, 2) < target else (lo, mid)
    return 0.5 * (lo + hi)


def match(p24eq):
    """Library scenario reached (largest library depth <= p24eq) and the next one up."""
    names = list(lib())
    depths = np.array(list(lib().values()))
    k = int(np.searchsorted(depths, p24eq, side="right")) - 1
    below = names[k] if k >= 0 else None
    above = names[k + 1] if k + 1 < len(names) else None
    return below, above


def rank(name):
    return -1 if name is None else list(lib()).index(name)


def assess(hourly_mm, antecedent_mm):
    """hourly_mm: pd.Series of corrected areal liquid rain (mm/h) indexed by UTC time."""
    s24 = hourly_mm.rolling(24, min_periods=1).sum()
    end = s24.idxmax()
    p24 = float(s24.max())
    window = hourly_mm[end - pd.Timedelta(hours=23):end]
    peak = window.idxmax() if p24 > 0 else end
    amc = amc_class(antecedent_mm)
    p24eq = amc_equivalent_depth(p24, amc)
    reached, next_up = match(p24eq)
    return {"p24_mm": round(p24, 1), "window_end": end.isoformat(), "peak_hour": peak.isoformat(),
            "antecedent_5d_mm": round(float(antecedent_mm), 1), "amc": amc, "p24_equivalent_mm": round(p24eq, 1),
            "scenario": reached, "next_scenario": next_up,
            "library_t0": (peak - pd.Timedelta(hours=DESIGN_BURST_H)).isoformat()}


def alert(det, members):
    """det: assessment of the reference deterministic model; members: assessments of ensemble members."""
    out = {"level": "green", "probabilities": {}}
    for scn in ("P25", "T2", "T5", "T10", "T25", "T50", "T100"):
        if scn in lib() and members:
            out["probabilities"][scn] = round(sum(rank(m["scenario"]) >= rank(scn) for m in members) / len(members), 3)
    for level in ("red", "orange", "yellow"):
        r = ALERT_RULES[level]
        if out["probabilities"].get(r["scenario"], 0) >= r["prob"] or rank(det["scenario"]) >= rank(r["deterministic"]):
            out["level"] = level
            break
    out["rules"] = ALERT_RULES
    return out
