"""Build the static data bundle for the web DSS (GitHub Pages). Usage: python -m pipeline.export.web

web/public/data/
  meta.json                  library, raster placement + channel encodings, sources, alert rules
  geo/*.geojson              catchment, subbasins, streams, villages, control points, buildings, roads, shelters
  scenarios/<name>/flood.png RGB: R depth (m x 40), G max velocity (m/s x 40), B first water > 0.1 m (h x 5, 0 = never)
  scenarios/<name>/time.png  RGB: R first water > 0.3 m (h x 5), G duration > 0.3 m (h x 5), B max d(v+0.5) (x 40)
  scenarios/<name>/impact.json  per-building + per-segment arrays (same order as the geojson), villages, actions
  hydrographs.json           HMS hydrographs (15 min) at every control point for every library storm
  mitigation.json, summary.json
PNG values are read back exactly in the browser (canvas getImageData), so the map can be queried.
"""

import json
import shutil

import geopandas as gpd
import numpy as np
from PIL import Image
from pyproj import Transformer

from pipeline import config, grid
from pipeline.hydraulics.scenarios import OUT as HYD, library
from pipeline.hydrology import hms, storms
from pipeline.impact import engine

WEB = config.WEB_DATA
_wgs = Transformer.from_crs(config.CRS_WORK, config.CRS_WEB, always_xy=True)
NEAR_DOMAIN_M = 150
RP_LABEL = {"P20": "below 2-year", "P25": "below 2-year", "P120": "beyond 500-year", "P140": "beyond 500-year",
            "P160": "beyond 500-year"}


def _q(a, scale, hi=255):
    return np.clip(np.round(a * scale), 0, hi).astype(np.uint8)


def window():
    act = np.load(HYD / "domain_active.npy")
    rows, cols = np.nonzero(act)
    return rows.min() - 2, rows.max() + 3, cols.min() - 2, cols.max() + 3


def corners(win):
    t, _, _ = grid.model_grid()
    r0, r1, c0, c1 = win
    pts = [t * (c0, r0), t * (c1, r0), t * (c1, r1), t * (c0, r1)]            # TL, TR, BR, BL
    return [list(np.round(_wgs.transform(x, y), 6)) for x, y in pts]


def rasters(name, win):
    r0, r1, c0, c1 = win
    d = HYD / name
    g = {k: grid.read(d / f"{k}.tif")[r0:r1, c0:c1] for k in
         ("hmax", "vmax", "hvmax", "t_arrival_01", "t_arrival_03", "duration_03")}
    wet = g["hmax"] >= 0.025
    t01 = np.where(wet & (g["t_arrival_01"] >= 0), np.maximum(g["t_arrival_01"], 0.2), 0)
    t03 = np.where(wet & (g["t_arrival_03"] >= 0), np.maximum(g["t_arrival_03"], 0.2), 0)
    flood = np.dstack([_q(np.where(wet, g["hmax"], 0), 40), _q(np.where(wet, g["vmax"], 0), 40), _q(t01, 5)])
    timing = np.dstack([_q(t03, 5), _q(np.where(wet, g["duration_03"], 0), 5), _q(np.where(wet, g["hvmax"], 0), 40)])
    out = WEB / "scenarios" / name
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(flood, "RGB").save(out / "flood.png", optimize=True)
    Image.fromarray(timing, "RGB").save(out / "time.png", optimize=True)


def to_wgs(gdf):
    return gdf.to_crs(config.CRS_WEB)


def write_geo(gdf, name, props, precision=5):
    gdf = to_wgs(gdf[props + ["geometry"]].copy())
    gdf.geometry = gdf.geometry.set_precision(10 ** -precision)
    (WEB / "geo" / name).write_text(gdf.to_json(drop_id=True, ensure_ascii=False), encoding="utf8")


def run():
    if WEB.exists():
        for sub in ("geo", "scenarios"):
            shutil.rmtree(WEB / sub, ignore_errors=True)
    (WEB / "geo").mkdir(parents=True, exist_ok=True)
    lib = {k: v for k, v in library().items() if (HYD / k / "run.json").exists()}
    win = window()

    # --- static vectors ----------------------------------------------------------------------
    b, s, p = engine.load_static()
    act = np.load(HYD / "domain_active.npy")
    from scipy import ndimage
    near = ndimage.binary_dilation(act, iterations=max(1, NEAR_DOMAIN_M // 30))
    t, w, h = grid.model_grid()
    cent = b.geometry.centroid
    col, row = ~t * (cent.x.values, cent.y.values)
    keep_b = near[np.clip(row.astype(int), 0, h - 1), np.clip(col.astype(int), 0, w - 1)] | (b["type"] != "residential")
    bweb = b[keep_b].copy()
    bweb["pop"] = bweb["pop"].round(1)
    bweb["facility_name"] = bweb["facility_name"].fillna("")
    write_geo(bweb, "buildings.geojson", ["village", "type", "pop", "facility_name"], 6)
    s["label"] = [engine_label(s, i) for i in range(len(s))]
    write_geo(s, "roads.geojson", ["highway", "ref", "label", "mode", "ford", "bridge", "length_m"], 5)
    places = p[(p["kind"] == "place") & p["name"].notna()].copy()
    places["name_local"] = places["name_local"].fillna("")
    write_geo(places, "villages.geojson", ["name", "name_local", "place"], 5)
    fac = p[p["kind"].isin(["school", "mosque", "health", "public", "tourism", "ford"])].copy()
    fac["name"] = fac["name"].fillna("")
    write_geo(fac, "facilities.geojson", ["kind", "name"], 5)
    for f in ("catchment.geojson", "subbasins.geojson", "streams.geojson", "control_points.geojson"):
        shutil.copy(config.INTERIM / f, WEB / "geo" / f)
    sh = json.loads((engine.OUT / "shelters.geojson").read_text(encoding="utf8"))
    for feat in sh["features"]:
        feat["geometry"]["coordinates"] = list(np.round(_wgs.transform(*feat["geometry"]["coordinates"]), 5))
    sh.pop("crs_epsg", None)
    for feat in sh["features"]:
        if not isinstance(feat["properties"].get("name"), str):
            feat["properties"]["name"] = None
    (WEB / "geo" / "shelters.geojson").write_text(json.dumps(sh, ensure_ascii=False), encoding="utf8")

    # --- per scenario --------------------------------------------------------------------------
    villages = json.loads((engine.OUT / "villages.json").read_text(encoding="utf8"))
    summary = json.loads((engine.OUT / "summary.json").read_text(encoding="utf8"))
    bidx = np.flatnonzero(keep_b.values if hasattr(keep_b, "values") else keep_b)
    for name in lib:
        rasters(name, win)
        sc = json.loads((engine.OUT / f"scenario_{name}.json").read_text(encoding="utf8"))
        acts = json.loads((engine.OUT / f"actions_{name}.json").read_text(encoding="utf8"))
        run_info = json.loads((HYD / name / "run.json").read_text(encoding="utf8"))
        bl = {k: [v[i] for i in bidx] for k, v in sc["buildings"].items()}
        (WEB / "scenarios" / name / "impact.json").write_text(json.dumps({
            "name": name, "p24_mm": lib[name], "buildings": bl, "segments": sc["segments"],
            "villages": villages[name], "actions": acts, "summary": summary["scenarios"][name], "hydraulics": run_info,
        }, ensure_ascii=False), encoding="utf8")

    # --- hydrographs at control points for every library storm ------------------------------------
    basin = hms.load_basin()
    hyd = {"dt_min": 15, "points": [{"id": sb.id, "name": sb.name, "kind": sb.kind, "drainage_km2": round(sb.drainage_km2, 1)}
                                    for sb in basin], "scenarios": {}}
    for name, p24 in lib.items():
        rain = storms.hyetograph_for_depth(p24, 731.0)
        res = hms.run_network(basin, lambda sb: rain)
        hyd["scenarios"][name] = {"rain_mm": np.round(rain.reshape(-1, 3).sum(axis=1), 2).tolist(),
                                  "q": {sb.id: np.round(res[sb.id]["total"][::3], 1).tolist() for sb in basin}}
    (WEB / "hydrographs.json").write_text(json.dumps(hyd), encoding="utf8")

    for f in ("mitigation.json",):
        shutil.copy(engine.OUT / f, WEB / f)
    idf = json.loads((config.INTERIM / "rainfall" / "idf.json").read_text(encoding="utf8"))
    checks = json.loads((config.RUNS / "hydrology" / "checks.json").read_text(encoding="utf8"))
    from pipeline.forecast import core
    meta = {
        "title": "Atlas - flash flood decision support, Ounila valley (Morocco)",
        "library": [{"name": n, "p24_mm": round(v, 1),
                     "return_period": RP_LABEL.get(n, f"{n[1:]}-year"),
                     **{k: summary["scenarios"][n][k] for k in ("buildings_affected", "people_affected", "road_km_closed",
                                                                "fords_closed", "villages_isolated")}} for n, v in lib.items()],
        "raster": {"corners_lonlat": corners(win), "width": int(win[3] - win[2]), "height": int(win[1] - win[0]),
                   "flood": {"r": ["depth_m", 40], "g": ["velocity_ms", 40], "b": ["first_water_01_h", 5]},
                   "time": {"r": ["first_water_03_h", 5], "g": ["duration_03_h", 5], "b": ["hv_max", 40]}},
        "design_burst_h": core.DESIGN_BURST_H, "alert_rules": core.ALERT_RULES,
        "correction_factor": core.correction(),
        "catchment_km2": 730.9, "population": 15571,
        "validation": {"water_balance": checks["water_balance"], "outlet_k": checks["outlet_k"]["central"],
                       "regional": checks["regional"]},
        "idf_t100_24h_mm": idf["scales"]["catchment"]["depth_mm"][5][5],
        # for the in-browser forecast (same logic as pipeline/forecast/core.py)
        "subbasins": [{"id": sb.id, "name": sb.name, "area_km2": round(sb.area_km2, 3), "cn": sb.cn} for sb in basin],
        "rain_points": [{"lon": round(float(x), 4), "lat": round(float(y), 4), "w": round(float(wt), 5)}
                        for (x, y), wt in zip(*_rain_points())],
        "amc_limits_mm": [12.7, 27.9],
    }
    (WEB / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf8")
    for f in list(WEB.rglob("*.json")) + list(WEB.rglob("*.geojson")):
        txt = f.read_text(encoding="utf8")
        json.loads(txt, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(f"{f}: {c} is not valid JSON")))
    total = sum(f.stat().st_size for f in WEB.rglob("*") if f.is_file())
    print(f"  web bundle: {len(lib)} scenarios, {len(bweb)} buildings, {len(s)} road segments, {total / 1e6:.1f} MB -> {WEB}")


def _rain_points():
    from pipeline.forecast.live import points
    return points()


def engine_label(s, i):
    import pandas as pd
    for col in ("name", "ref"):
        v = s[col].iloc[i]
        if pd.notna(v) and v:
            return str(v)
    return f"{s['highway'].iloc[i]} road"


if __name__ == "__main__":
    run()
