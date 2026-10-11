"""Mitigation what-if, evaluated with the models (not rules of thumb).

Usage: python -m pipeline.impact.mitigation        (after impact.engine)

restoration   rangeland restoration / reforestation of the headwater sub-basins: CN lowered (AMC II).
              HMS is re-run; every village's impacts are read off the 2D library at the new peak of its
              control point (impacts interpolated against that point's library peaks).
check_dams    a series of gabion check dams per headwater sub-basin: their storage is filled first from
              each local hydrograph. Effective for small floods, small for large ones (shown, not hidden).
crossings     flood-proof the road links that cut villages off: each 4WD-unsafe segment on an isolated
              village's normal route to the RN9 is charged that village's isolation hours; the top links
              are then raised/protected together and isolation recomputed on the full network.
No costs are invented: the DSS shows effectiveness; planners enter local unit costs in the interface.
Output: data/runs/impact/mitigation.json
"""

import json

import geopandas as gpd
import numpy as np
import pandas as pd

from pipeline import config, grid
from pipeline.hydraulics.scenarios import library
from pipeline.hydrology import hms, storms
from pipeline.impact import engine

HEADWATERS_CN_DROP = 6.0          # CN reduction from restored cover (poor -> fair rangeland, TR-55 ~5-8)
CHECK_DAMS = 25                   # per headwater sub-basin
CHECK_DAM_M3 = 1500.0             # storage per small gabion check dam (m3)
RAISE_TOP = 10
RAISE_M = 1.0
EVAL = ("T10", "T100")



def _label(s, i):
    for col in ("name", "ref"):
        v = s[col].iloc[i]
        if pd.notna(v) and v:
            return str(v)
    return f"{s['highway'].iloc[i]} road"

def headwaters(basin):
    """Sub-basins with no upstream sub-basin."""
    has_up = {sb.downstream for sb in basin}
    return [sb.id for sb in basin if sb.id not in has_up]


def control_point_of_villages(villages):
    p = gpd.read_file(engine.PREP / "pois.gpkg")
    p = p[(p["kind"] == "place") & p["name"].isin(villages)]
    labels = grid.read(config.INTERIM / "subbasins.tif")
    t, w, h = grid.model_grid()
    out = {}
    for _, r in p.iterrows():
        col, row = ~t * (r.geometry.x, r.geometry.y)
        lab = int(labels[min(max(int(row), 0), h - 1), min(max(int(col), 0), w - 1)])
        out[r["name"]] = lab if lab > 0 else 1
    return out


def library_peaks(basin):
    """Peak at every control point for each library storm (outlet storm, as in the 2D runs)."""
    peaks = {}
    for name, p24 in library().items():
        rain = storms.hyetograph_for_depth(p24, 731.0)
        res = hms.run_network(basin, lambda sb: rain)
        peaks[name] = {sb.id: float(res[sb.id]["total"].max()) for sb in basin}
    return peaks


def interp_impacts(villages_by_scn, cp_of, lib_peaks, new_peaks):
    """Village impacts at new control-point peaks, interpolated over the library."""
    names = [n for n in library() if n in villages_by_scn]
    out = {}
    for v, cp in cp_of.items():
        q = np.array([lib_peaks[n][cp] for n in names])
        order = np.argsort(q)
        q = q[order]
        rec = {}
        for key in ("buildings_affected", "people_affected", "collapse_possible"):
            y = np.array([villages_by_scn[n][v][key] for n in names])[order]
            rec[key] = float(np.interp(new_peaks[cp], q, y))
        out[v] = rec
    return out


def _totals(imp):
    return {k: round(sum(v[k] for v in imp.values()), 1) for k in ("buildings_affected", "people_affected", "collapse_possible")}


def hms_measure(basin, scn_p24, modify):
    rain = storms.hyetograph_for_depth(scn_p24, 731.0)
    b2 = modify(basin)
    res = hms.run_network(b2, lambda sb: rain)
    return {sb.id: float(res[sb.id]["total"].max()) for sb in b2}


def check_dam_network(basin, rain, storage_m3):
    """run_network with each headwater local hydrograph reduced by a fill-first storage."""
    n = len(rain)
    res = {}
    for sb in basin:
        local, _ = hms.subbasin_hydrograph(rain, sb, 2, n)
        if sb.id in storage_m3:
            cum = np.cumsum(local) * hms.DT_S
            local = np.where(cum <= storage_m3[sb.id], 0.0, local)
            k = np.argmax(cum > storage_m3[sb.id])
            if cum[-1] > storage_m3[sb.id]:
                local[k] = (cum[k] - storage_m3[sb.id]) / hms.DT_S
        total = local.copy()
        for up in basin:
            if up.downstream == sb.id:
                total += hms.route(res[up.id], up.reach)[:n]
        res[sb.id] = total
    return {i: float(q.max()) for i, q in res.items()}


def critical_links(scn):
    """Which flooded road links cut villages off? For every isolated village take its normal (dry)
    shortest route to the RN9; each 4WD-unsafe segment on it is charged that village's isolation hours.
    The top links are then flood-proofed together (raised crossing / protected embankment: unsafe only
    above the 4WD limit + RAISE_M) and isolation is recomputed on the full network."""
    import networkx as nx
    from pyproj import Transformer
    b, s, p = engine.load_static()
    g = engine.build_graph(s)
    anc = engine.anchors(s, g)
    vnodes = engine.village_nodes(p, s, g)
    r, snaps = engine.scenario_rasters(scn)
    sm = engine.segment_metrics(s, r, snaps, engine.domain_index())
    wd = sm["_wd"]
    iso, unreachable = engine.isolation(g, anc, vnodes, wd)
    g2 = g.copy()
    for a in anc:
        g2.add_edge("RN9", a, seg=-1, length=0.0)
    charge = {}
    for v, x in iso.items():
        if not x:
            continue
        path = nx.shortest_path(g2, vnodes[v]["node"], "RN9", weight="length")
        segs = [g2.edges[u, w]["seg"] for u, w in zip(path[:-1], path[1:]) if g2.edges[u, w]["seg"] >= 0]
        for k in segs:
            if wd[k].any():
                charge[k] = charge.get(k, 0.0) + x["hours"]
    ranked = sorted(charge.items(), key=lambda kv: -kv[1])
    top = [k for k, _ in ranked[:RAISE_TOP]]
    didx = engine.domain_index()
    m = wd.copy()
    for k in top:
        dom = didx[s["cell_list"].iloc[k]]
        dom = dom[dom >= 0]
        if len(dom):
            m[k] = snaps[:, dom].max(axis=1) > 0.5 + RAISE_M
    iso2, _ = engine.isolation(g, anc, vnodes, m)
    to_wgs = Transformer.from_crs(config.CRS_WORK, config.CRS_WEB, always_xy=True)

    def info(k, hours):
        c = s.geometry.iloc[k].interpolate(0.5, normalized=True)
        return {"segment": int(k), "village_hours_charged": hours, "ford": bool(s["ford"].iloc[k]),
                "highway": s["highway"].iloc[k], "label": _label(s, k),
                "max_depth_m": round(float(sm["depth"][k]), 2), "lonlat": [round(v, 5) for v in to_wgs.transform(c.x, c.y)]}
    vh = lambda d: round(sum(x["hours"] for x in d.values() if x), 1)
    return {"baseline_village_hours": vh(iso), "baseline_isolated": sorted(v for v, x in iso.items() if x),
            "ranked_links": [info(k, h) for k, h in ranked], "flood_proofed": top,
            "with_works_village_hours": vh(iso2), "with_works_isolated": sorted(v for v, x in iso2.items() if x),
            "reconnected": sorted(v for v, x in iso.items() if x and not iso2.get(v))}


def run():
    basin = hms.load_basin()
    villages = json.loads((engine.OUT / "villages.json").read_text(encoding="utf8"))
    lib = library()
    cp_of = control_point_of_villages(next(iter(villages.values())).keys())
    lib_peaks = library_peaks(basin)
    hw = headwaters(basin)
    area_hw = sum(sb.area_km2 for sb in basin if sb.id in hw)
    out = {"headwater_subbasins": hw, "headwater_area_km2": round(area_hw, 1), "measures": {}}

    for scn in EVAL:
        p24 = lib[scn]
        base_peaks = lib_peaks[scn]
        base = interp_impacts(villages, cp_of, lib_peaks, base_peaks)

        def restore(b):
            import copy
            b2 = copy.deepcopy(b)
            for sb in b2:
                if sb.id in hw:
                    sb.cn = max(sb.cn - HEADWATERS_CN_DROP, 30.0)
            return b2
        pk_r = hms_measure(basin, p24, restore)
        rain = storms.hyetograph_for_depth(p24, 731.0)
        pk_c = check_dam_network(basin, rain, {i: CHECK_DAMS * CHECK_DAM_M3 for i in hw})
        rec = {"baseline": {"outlet_peak_m3s": round(base_peaks[1], 1), **_totals(base)}}
        for key, pk, desc in (("restoration", pk_r, f"CN -{HEADWATERS_CN_DROP} on {len(hw)} headwater sub-basins ({area_hw:.0f} km2)"),
                              ("check_dams", pk_c, f"{CHECK_DAMS} check dams x {CHECK_DAM_M3:.0f} m3 in each of {len(hw)} headwater sub-basins")):
            imp = interp_impacts(villages, cp_of, lib_peaks, pk)
            tot = _totals(imp)
            rec[key] = {"description": desc, "outlet_peak_m3s": round(pk[1], 1),
                        "peak_reduction_pct": round(100 * (1 - pk[1] / base_peaks[1]), 1), **tot,
                        "avoided": {k: round(rec["baseline"][k] - tot[k], 1) for k in tot}}
        rec["crossings"] = {"description": f"flood-proof the {RAISE_TOP} road links that cut most villages off "
                                           f"(raised crossing / protected embankment, +{RAISE_M} m)", **critical_links(scn)}
        out["measures"][scn] = rec
        r = rec
        print(f"  {scn}: outlet {r['baseline']['outlet_peak_m3s']} m3/s | restoration -{r['restoration']['peak_reduction_pct']}% peak, "
              f"-{r['restoration']['avoided']['buildings_affected']:.0f} bldg | check dams {-r['check_dams']['peak_reduction_pct']:+.1f}% peak | "
              f"links: isolation {r['crossings']['baseline_village_hours']} -> {r['crossings']['with_works_village_hours']} village-hours, "
              f"reconnected {len(r['crossings']['reconnected'])}/{len(r['crossings']['baseline_isolated'])}")
    (engine.OUT / "mitigation.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")


if __name__ == "__main__":
    run()
