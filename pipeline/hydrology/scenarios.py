"""Design-flood runs, water-balance check, sensitivity and regional comparison for the HMS engine.

Usage: python -m pipeline.hydrology.scenarios

Outputs (data/runs/hydrology/):
  design.json        hydrographs (15 min) for every return period x rainfall level, two storm sets:
                       point_specific  storm areal-reduced to each control point's drainage area (as
                                       HEC-HMS frequency storms are run per analysis point) - use for
                                       per-village peaks
                       outlet_storm    one storm sized to the whole catchment - consistent inflows for
                                       the 2D model
  checks.json        water balance vs the Agouillal gauge, Francou-Rodier K, sensitivity table
"""

import json

import numpy as np
import pandas as pd

from pipeline import config
from pipeline.data import rainfall as rf
from pipeline.hydrology import hms, storms

OUT = config.RUNS / "hydrology"
OUT.mkdir(parents=True, exist_ok=True)
SAMPLE = 3                         # store every 3rd 5-min step -> 15 min

# Observed reference data (see docs/hydrology.md for sources)
AGOUILLAL = {"area_km2": 740, "mean_flow_m3s": 1.3, "period": "1976/77-1997/98",
             "source": "Agoussine et al. 2004, Bull. Inst. Sci. Rabat 26:81-92 (DRPE data)"}
STORM_RUNOFF_SHARE = (0.35, 0.65)  # share of total runoff from storms (rest: snowmelt + baseflow),
                                   # read from the Agouillal monthly regime (Agoussine et al. 2004, Fig. 9)
REGIONAL = [   # (name, area km2, peak m3/s, what it is)
    ("Ourika at Aghbalou Q10", 503, 485, "Saidi et al. 2010 (ABH Tensift gauge)"),
    ("Ourika at Aghbalou Q2", 503, 103, "Saidi et al. 2010"),
    ("Ourika 17 Aug 1995 (record)", 503, 1030, "Saidi et al. 2010"),
    ("Ourika 28 Oct 1999", 503, 762, "Saidi et al. 2010"),
    ("Ourika 2 Nov 1987", 503, 650, "Saidi et al. 2010"),
]


def francou_rodier_k(q, area_km2):
    return 10.0 * (1.0 - np.log10(q / 1e6) / np.log10(area_km2 / 1e8))


def _pack(q, sb):
    return {"peak_m3s": round(float(q.max()), 2),
            "time_to_peak_h": round(float(np.argmax(q) * hms.DT_S / 3600.0), 2),
            "volume_hm3": round(float(q.sum() * hms.DT_S / 1e6), 4),
            "k_francou_rodier": round(float(francou_rodier_k(max(q.max(), 1e-3), sb.drainage_km2)), 3),
            "q": np.round(q[::SAMPLE], 2).tolist()}


def run_design(basin):
    results = {}
    for level in rf.LEVELS:
        results[level] = {}
        for T in rf.RETURN_PERIODS:
            outlet_rain = storms.design_hyetograph(T, level, max(s.drainage_km2 for s in basin))
            outlet_res = hms.run_network(basin, lambda sb: outlet_rain)
            point = {}
            for sb in basin:
                rain = storms.design_hyetograph(T, level, sb.drainage_km2)
                point[sb.id] = _pack(hms.run_network(basin, lambda _: rain)[sb.id]["total"], sb)
            results[level][str(T)] = {
                "outlet_storm": {sb.id: _pack(outlet_res[sb.id]["total"], sb) for sb in basin},
                "outlet_storm_rain_mm": np.round(outlet_rain[::SAMPLE] * SAMPLE, 3).tolist(),
                "point_specific": point,
            }
            print(f"  {level:7s} T{T:<4} outlet peak {point[1]['peak_m3s']:7.1f} m3/s")
    return results


def water_balance(basin, levels, cn_shift=0.0):
    """Event-based SCS-CN runoff from ERA5-Land liquid hourly rain, 1976/77-1997/98, AMC from the
    5-day antecedent rain (NEH-4 dormant-season limits), against the Agouillal gauge."""
    idx, lonlat, liq = rf.load_era5()
    areal = pd.Series((rf.catchment_weights(lonlat)[:, None] * liq).sum(axis=0), index=idx)
    sel = areal["1976-09-01":"1998-08-31"].values
    years = 22
    events, start, dry = [], None, 0          # storms separated by >= 12 h below 0.1 mm/h
    for i, v in enumerate(sel > 0.1):
        if v:
            start = i if start is None else start
            dry, end = 0, i
        elif start is not None:
            dry += 1
            if dry >= 12:
                events.append((start, end))
                start = None
    areas = np.array([s.area_km2 for s in basin])
    cn2 = np.array([s.cn for s in basin]) + cn_shift
    observed_mm = AGOUILLAL["mean_flow_m3s"] * 365.25 * 86400 / (AGOUILLAL["area_km2"] * 1e6) * 1000
    out = {"observed_total_runoff_mm_yr": round(observed_mm, 1),
           "storm_share_range": STORM_RUNOFF_SHARE,
           "observed_storm_runoff_mm_yr": [round(observed_mm * f, 1) for f in STORM_RUNOFF_SHARE],
           "n_events": len(events), "levels": {}}
    for level, f in levels.items():
        total = 0.0
        for s, e in events:
            p = sel[s:e + 1].sum() * f
            ante = sel[max(0, s - 120):s].sum() * f
            amc = 1 if ante < 12.7 else (3 if ante > 27.9 else 2)
            cn = np.clip([hms.cn_amc(c, amc) for c in cn2], 30, 98)
            S = 25400.0 / cn - 254.0
            q = np.where(p > 0.2 * S, (p - 0.2 * S) ** 2 / (p + 0.8 * S), 0.0)
            total += float((q * areas).sum() / areas.sum())
        out["levels"][level] = {"factor": f, "precip_mm_yr": round(float(sel.sum() * f / years), 0),
                                "storm_runoff_mm_yr": round(total / years, 1)}
    return out


def sensitivity():
    rows = []
    variants = [("adopted: Tc mean(Giandotti,Temez), R = 1.0 Tc", hms.TC_FORMULAS, 1.0, hms.WIDTH_COEF),
                ("R = 0.5 Tc", hms.TC_FORMULAS, 0.5, hms.WIDTH_COEF),
                ("R = 1.5 Tc", hms.TC_FORMULAS, 1.5, hms.WIDTH_COEF),
                ("Tc incl. Kirpich, R = 1.0 Tc", ("kirpich", "giandotti", "temez"), 1.0, hms.WIDTH_COEF),
                ("Tc Giandotti only", ("giandotti",), 1.0, hms.WIDTH_COEF),
                ("Tc Temez only", ("temez",), 1.0, hms.WIDTH_COEF),
                ("channel width x2", hms.TC_FORMULAS, 1.0, hms.WIDTH_COEF * 2),
                ("channel width x0.5", hms.TC_FORMULAS, 1.0, hms.WIDTH_COEF / 2)]
    for label, keys, r, wc in variants:
        basin = hms.load_basin(r_over_tc=r, width_coef=wc)
        for s in basin:
            s.tc_h = max(float(np.mean([s.tc_formulas_h[k] for k in keys])), 0.25)
            s.r_h = r * s.tc_h
        row = {"variant": label}
        for T in (2, 10, 100):
            rain = storms.design_hyetograph(T, "central", 731)
            row[f"Q{T}"] = round(float(hms.run_network(basin, lambda sb: rain)[1]["total"].max()), 1)
        rows.append(row)
    return rows


def run():
    basin = hms.load_basin()
    idf = storms.idf()
    meta = {
        "dt_s": hms.DT_S, "stored_dt_min": hms.DT_S * SAMPLE // 60, "sim_hours": hms.SIM_HOURS,
        "methods": {"loss": "SCS CN, Ia = 0.2 S, AMC II", "transform": "Clark UH (HEC-HMS synthetic time-area)",
                    "routing": "variable-parameter Muskingum-Cunge", "baseflow": "none"},
        "params": {"tc_formulas": hms.TC_FORMULAS, "r_over_tc": hms.R_OVER_TC, "channel_n": hms.CHANNEL_N,
                   "width": f"{hms.WIDTH_COEF} * sqrt(drainage km2) m"},
        "rain_levels": idf["correction_levels"], "return_periods": rf.RETURN_PERIODS,
        "points": [{"id": s.id, "name": s.name, "kind": s.kind, "drainage_km2": round(s.drainage_km2, 2),
                    "area_km2": s.area_km2, "cn": s.cn, "tc_h": round(s.tc_h, 3), "r_h": round(s.r_h, 3),
                    "tc_formulas_h": s.tc_formulas_h, "downstream": s.downstream, "reach": s.reach} for s in basin],
    }
    print("[hydrology] design runs")
    results = run_design(basin)
    (OUT / "design.json").write_text(json.dumps({"meta": meta, "results": results}), encoding="utf8")

    print("[hydrology] checks")
    wb = water_balance(basin, idf["correction_levels"])
    sens = sensitivity()
    outlet = {lv: {T: results[lv][str(T)]["point_specific"][1]["peak_m3s"] for T in rf.RETURN_PERIODS}
              for lv in rf.LEVELS}
    checks = {
        "water_balance": wb, "sensitivity_outlet": sens, "outlet_peaks": outlet,
        "outlet_k": {lv: {T: round(float(francou_rodier_k(q, 730.9)), 2) for T, q in v.items()} for lv, v in outlet.items()},
        "regional": [{"name": n, "area_km2": a, "peak_m3s": q, "k": round(float(francou_rodier_k(q, a)), 2), "source": src}
                     for n, a, q, src in REGIONAL],
        "agouillal": AGOUILLAL,
    }
    (OUT / "checks.json").write_text(json.dumps(checks, indent=1), encoding="utf8")

    print(f"  water balance, observed storm runoff {wb['observed_storm_runoff_mm_yr']} mm/yr: " +
          ", ".join(f"{lv} {v['storm_runoff_mm_yr']}" for lv, v in wb["levels"].items()))
    print("  outlet peaks (m3/s) and Francou-Rodier K, central: " +
          ", ".join(f"T{T} {q:.0f} (K {checks['outlet_k']['central'][T]})" for T, q in outlet["central"].items()))
    for r in sens:
        print(f"    {r['variant']:48s} Q2 {r['Q2']:6.0f}  Q10 {r['Q10']:6.0f}  Q100 {r['Q100']:6.0f}")


if __name__ == "__main__":
    run()
