"""HEC-RAS 2D cross-check package for the Tamdaght -> Ait Ben Haddou reach, plus this solver's answer.

Usage: python -m pipeline.hydraulics.hec_ras_export     (after pipeline.hydraulics.scenarios)

The test reach is the 2D domain inside the two lowest sub-basins (Tamdaght, Ait Ben Haddou) plus the
downstream extension. Inflows are the two branches meeting at Tamdaght (Tazlaft = western Ounila,
Taifest = eastern Marghene), T100 central, outlet storm; the small local inflows of the two reach
sub-basins are left out on both sides so the comparison is purely hydraulic.

Writes hec/ras/Ounila_reach/:
  terrain_utm29n.tif        2D terrain (raw GLO-30 with breached channels), the same surface this solver uses
  landcover_classes.tif     ESA WorldCover class per cell, 200 = channel; + landcover_manning.csv
  perimeter.shp             2D flow area
  bc_inflow_*.shp / .csv    upstream boundary-condition lines and flow hydrographs (15 min)
  bc_outflow.shp            downstream boundary line, normal depth slope in README
  expected_hmax_m.tif       max depth from this solver for the same set-up
  expected_summary.json
"""

import csv
import json

import geopandas as gpd
import numpy as np
import shapely.geometry as sg
from rasterio import features

from pipeline import config, grid
from pipeline.data import landsurface
from pipeline.hydraulics import lisflood2d as lf
from pipeline.hydraulics import scenarios as sc
from pipeline.hydrology import hms, storms

RAS_DIR = config.HEC / "ras" / "Ounila_reach"
REACH_SUBBASINS = (1, 2)            # Ait Ben Haddou, Tamdakhte
INFLOW_FROM = {3: "Tazlaft", 6: "Taifest"}
T, P24 = 100, None
BC_HALF_WIDTH = 8                   # cells either side of the entry cell for the inflow line


def _line_across(rc, active, transform, flow_dir_code):
    """A boundary line through cell rc, perpendicular to the D8 flow direction, clipped to active cells."""
    dr, dc = sc.DIRMAP[int(flow_dir_code)]
    pr, pc = -dc, dr                                    # perpendicular in (row, col)
    pts = []
    for k in range(-BC_HALF_WIDTH, BC_HALF_WIDTH + 1):
        r, c = rc[0] + k * pr, rc[1] + k * pc
        if 0 <= r < active.shape[0] and 0 <= c < active.shape[1] and active[r, c]:
            pts.append(transform * (c + 0.5, r + 0.5))
    return sg.LineString(pts) if len(pts) >= 2 else sg.LineString([transform * (rc[1], rc[0] + 0.5),
                                                                     transform * (rc[1] + 1, rc[0] + 0.5)])


def run():
    RAS_DIR.mkdir(parents=True, exist_ok=True)
    transform, _, _ = grid.model_grid()
    dom, fd, catch, acc = sc.build_domain()
    labels = grid.read(config.INTERIM / "subbasins.tif")
    z2d = grid.read(sc.OUT / "dem_2d.tif").astype(np.float64)
    nman = grid.read(config.INTERIM / "manning.tif").astype(np.float64)
    full = dom["active"]
    sub = full & (np.isin(labels, REACH_SUBBASINS) | dom["ext"])
    from scipy import ndimage
    lab, _ = ndimage.label(sub)
    sub = lab == lab[dom["outlet_rc"]]

    # inflow entry cells: where each branch's D8 path first enters the sub-domain
    model = json.loads((config.INTERIM / "basin_model.json").read_text(encoding="utf8"))
    entries = {}
    for sb in model["subbasins"]:
        if sb["id"] in INFLOW_FROM:
            col, row = ~transform * tuple(sb["outlet_xy"])
            r, c = int(row), int(col)
            for _ in range(2000):
                if sub[r, c]:
                    break
                dr, dc = sc.DIRMAP[int(fd[r, c])]
                r, c = r + dr, c + dc
            entries[sb["id"]] = (r, c)

    basin = hms.load_basin()
    rain = storms.design_hyetograph(T, "central", 731.0)
    res_h = hms.run_network(basin, lambda s: rain)
    hydro = {sid: res_h[sid]["total"] for sid in INFLOW_FROM}

    # this solver on the same sub-domain and boundary conditions
    sdom = lf.build(sub, z2d, nman)
    out_cells = [sdom["idx"][dom["rows"][i], dom["cols"][i]] for i in dom["outlets"][0]]
    src = ([sdom["idx"][entries[s]] for s in INFLOW_FROM], list(range(len(INFLOW_FROM))), [1.0] * len(INFLOW_FROM))
    q_in = np.array([hydro[s] for s in INFLOW_FROM])
    res = lf.simulate(sdom, src, q_in, hms.DT_S, 0.0, sc.SIM_T1_H * 3600, (out_cells, dom["outlets"][1]))
    hmax = np.full(sub.shape, 0.0, dtype="float32")
    hmax[sdom["rows"], sdom["cols"]] = res["hmax"]

    # --- write the package (clipped to the sub-domain bbox + 20 cells) ---------------------------
    rows, cols = np.nonzero(sub)
    r0, r1 = max(rows.min() - 20, 0), rows.max() + 21
    c0, c1 = max(cols.min() - 20, 0), cols.max() + 21
    win_t = transform * transform.translation(c0, r0)
    import rasterio
    prof = dict(driver="GTiff", crs=config.CRS_WORK, transform=win_t, width=c1 - c0, height=r1 - r0, count=1,
                compress="deflate")
    raw = grid.read(config.RAW / "dem.tif")
    terrain = np.where(z2d > -9000, z2d, raw)[r0:r1, c0:c1].astype("float32")
    with rasterio.open(RAS_DIR / "terrain_utm29n.tif", "w", dtype="float32", nodata=-9999, **prof) as dst:
        dst.write(terrain, 1)
    wc = grid.read(config.RAW / "worldcover.tif").astype("uint8")
    wc = np.where(acc >= landsurface.CHANNEL_KM2, 200, wc).astype("uint8")
    with rasterio.open(RAS_DIR / "landcover_classes.tif", "w", dtype="uint8", nodata=0, **prof) as dst:
        dst.write(wc[r0:r1, c0:c1], 1)
    with open(RAS_DIR / "landcover_manning.csv", "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["class", "description", "mannings_n"])
        names = {10: "tree cover", 20: "shrubland", 30: "grassland", 40: "cropland", 50: "built-up",
                 60: "bare/sparse", 70: "snow/ice", 80: "water", 90: "wetland", 100: "moss/lichen",
                 200: "channel (drainage >= 5 km2)"}
        for k, v in landsurface.MANNING.items():
            w.writerow([k, names[k], v])
        w.writerow([200, names[200], landsurface.CHANNEL_N])
    with rasterio.open(RAS_DIR / "expected_hmax_m.tif", "w", dtype="float32", nodata=0, **prof) as dst:
        dst.write(hmax[r0:r1, c0:c1], 1)

    perim = sg.shape(next(s for s, v in features.shapes(sub.astype("uint8"), transform=transform) if v == 1))
    gpd.GeoDataFrame({"name": ["Ounila_reach"]}, geometry=[perim], crs=config.CRS_WORK).to_file(RAS_DIR / "perimeter.shp")
    for sid, name in INFLOW_FROM.items():
        line = _line_across(entries[sid], sub, transform, fd[entries[sid]])
        gpd.GeoDataFrame({"name": [f"in_{name}"]}, geometry=[line], crs=config.CRS_WORK).to_file(RAS_DIR / f"bc_inflow_{name}.shp")
        with open(RAS_DIR / f"bc_inflow_{name}.csv", "w", newline="", encoding="utf8") as f:
            w = csv.writer(f)
            w.writerow(["hours_from_start", "flow_m3s"])
            for i, q in enumerate(hydro[sid][::3]):
                w.writerow([round(i * 0.25, 2), round(float(q), 2)])
    out_pts = [transform * (dom["cols"][i] + 0.5, dom["rows"][i] + 0.5) for i in dom["outlets"][0]]
    out_line = sg.MultiPoint(out_pts).minimum_rotated_rectangle
    out_line = sg.LineString(list(out_line.exterior.coords)[:2]) if out_line.geom_type == "Polygon" else out_line
    gpd.GeoDataFrame({"name": ["out_normal_depth"]}, geometry=[out_line], crs=config.CRS_WORK).to_file(RAS_DIR / "bc_outflow.shp")

    summary = {"return_period": T, "inflow_peaks_m3s": {INFLOW_FROM[s]: round(float(hydro[s].max()), 1) for s in INFLOW_FROM},
               "outflow_normal_depth_slope": round(float(dom["outlets"][1][0]), 5),
               "cells": int(sub.sum()), "area_km2": round(float(sub.sum() * 0.0009), 2),
               "expected_peak_outflow_m3s": round(float(res["outflow"].max()), 1),
               "expected_flooded_km2_gt_0.1m": round(float((res["hmax"] > 0.1).sum() * 0.0009), 2),
               "expected_max_depth_m": round(float(res["hmax"].max()), 2), "mass_error": round(res["mass_error"], 5)}
    (RAS_DIR / "expected_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf8")
    print(f"  HEC-RAS package -> {RAS_DIR}: {summary}")


if __name__ == "__main__":
    run()
