"""Terrain processing: DEM conditioning, flow grids, catchment, streams, HAND and sub-basins.

Usage: python -m pipeline.data.terrain

Outputs (data/interim/):
  dem_cond.tif, fdir.tif (D8, ESRI codes), acc_km2.tif, hand.tif, catchment.tif, subbasins.tif
  catchment.geojson, streams.geojson, subbasins.geojson, control_points.geojson   (all WGS84)
  basin_model.json   - sub-basin + reach topology/attributes consumed by the HMS engine
"""

import json

import numpy as np
import rasterio.features
import shapely.geometry as sg
from pyproj import Transformer
from pysheds.grid import Grid
from pysheds.view import Raster
import shapely
from shapely.ops import unary_union

from pipeline import config, grid

INTERIM = config.INTERIM
CELL_KM2 = (config.GRID_RES_M / 1000) ** 2

OUTLET = ("Ait Ben Haddou", -7.131, 31.045)   # catchment outlet (lon, lat)
STREAM_KM2 = 1.0           # drainage area that starts a mapped stream
CONTROL_STREAM_KM2 = 5.0   # villages are snapped to channels at least this big
VILLAGE_SNAP_M = 500       # max distance from a village to its channel
CONFLUENCE_KM2 = 25.0      # both branches above this -> sub-basin break at the junction
MIN_SUBBASIN_KM2 = 3.0     # confluence increments below this merge downstream
MIN_VILLAGE_KM2 = 0.5      # villages keep their own sub-basin (and hydrograph) unless essentially zero

_to_utm = Transformer.from_crs(config.CRS_WEB, config.CRS_WORK, always_xy=True)
_to_wgs = Transformer.from_crs(config.CRS_WORK, config.CRS_WEB, always_xy=True)


def _wgs(geom):
    return shapely.transform(geom, lambda a: np.column_stack(_to_wgs.transform(a[:, 0], a[:, 1])))


def _write_geojson(name, features):
    path = INTERIM / name
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf8")
    return path


def _polygonize(mask, transform):
    shapes = [sg.shape(s) for s, v in rasterio.features.shapes(mask.astype("uint8"), transform=transform) if v == 1]
    return unary_union(shapes)


def run():
    transform, width, height = grid.model_grid()
    g = Grid.from_raster(str(config.RAW / "dem.tif"))
    dem_raw = g.read_raster(str(config.RAW / "dem.tif"))
    dem = g.resolve_flats(g.fill_depressions(g.fill_pits(dem_raw)))
    fdir = g.flowdir(dem)
    acc = g.accumulation(fdir)
    acc_km2 = np.asarray(acc) * CELL_KM2

    def R(mask):  # pysheds wants its own Raster type for masks
        return Raster(np.asarray(mask), viewfinder=acc.viewfinder)
    print(f"  flow grids done, max drainage {acc_km2.max():.0f} km2")

    # --- catchment -------------------------------------------------------------
    ox, oy = _to_utm.transform(OUTLET[1], OUTLET[2])
    ox, oy = g.snap_to_mask(R(acc_km2 > CONTROL_STREAM_KM2), (ox, oy))
    oc, orow = ~transform * (ox, oy)
    catch = np.asarray(g.catchment(x=int(oc), y=int(orow), fdir=fdir, xytype="index")).astype(bool)
    print(f"  catchment above {OUTLET[0]}: {catch.sum() * CELL_KM2:.1f} km2")

    streams_mask = (acc_km2 >= STREAM_KM2) & catch
    hand = np.asarray(g.compute_hand(fdir, dem, R(acc_km2 >= STREAM_KM2)), dtype="float32")
    hand[~catch] = -9999

    # --- control points: outlet, villages on channels, major confluences ----------
    controls = [{"name": OUTLET[0], "kind": "outlet", "x": float(ox), "y": float(oy)}]
    places = json.loads((config.RAW / "osm_places.geojson").read_text(encoding="utf8"))["features"]
    chan_arr = (acc_km2 >= CONTROL_STREAM_KM2) & catch
    for f in places:
        p = f["properties"]
        if p["place"] not in ("town", "village") or not p["name"]:
            continue
        x, y = _to_utm.transform(*f["geometry"]["coordinates"])
        col, row = ~transform * (x, y)
        if not (0 <= row < height and 0 <= col < width) or not catch[int(row), int(col)]:
            continue
        # snap to the LARGEST channel within VILLAGE_SNAP_M (the main wadi is the dominant hazard)
        rad = int(VILLAGE_SNAP_M // config.GRID_RES_M)
        r0, c0 = int(row), int(col)
        rr, cc = np.mgrid[max(r0 - rad, 0):min(r0 + rad + 1, height), max(c0 - rad, 0):min(c0 + rad + 1, width)]
        inside = (np.hypot(rr - r0, cc - c0) <= rad) & chan_arr[rr, cc]
        if not inside.any():
            continue
        k = np.argmax(np.where(inside, acc_km2[rr, cc], -1))
        sx, sy = transform * (cc.flat[k] + 0.5, rr.flat[k] + 0.5)
        controls.append({"name": p["name"], "kind": "village", "x": float(sx), "y": float(sy),
                         "village_lon": f["geometry"]["coordinates"][0], "village_lat": f["geometry"]["coordinates"][1]})

    # Junctions: a cell whose two largest D8 donors both drain > CONFLUENCE_KM2
    fd = np.asarray(fdir)
    dirmap = {64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1)}
    big = (acc_km2 > CONFLUENCE_KM2) & catch
    donors = {}
    for r, c in zip(*np.nonzero(big)):
        dr, dc = dirmap.get(int(fd[r, c]), (0, 0))
        if dr or dc:
            donors.setdefault((r + dr, c + dc), []).append((r, c))
    for (r, c), ds in donors.items():
        if len(ds) >= 2 and catch[r, c]:
            x, y = transform * (c + 0.5, r + 0.5)
            controls.append({"name": f"Confluence {acc_km2[r, c]:.0f} km2", "kind": "confluence",
                             "x": float(x), "y": float(y)})

    # --- downstream topology on the D8 grid ---------------------------------------------
    def cell_of(cp):
        col, row = ~transform * (cp["x"], cp["y"])
        return int(row), int(col)

    def next_cell(r, c):
        dr, dc = dirmap.get(int(fd[r, c]), (0, 0))
        r2, c2 = r + dr, c + dc
        if (dr or dc) and 0 <= r2 < height and 0 <= c2 < width and catch[r2, c2]:
            return r2, c2
        return None

    # Flow length to the catchment outlet (m), true D8 step lengths. Cells are visited in
    # increasing drainage order reversed (downstream first), so the downstream value exists.
    step = {k: config.GRID_RES_M * (np.sqrt(2) if dr and dc else 1.0) for k, (dr, dc) in dirmap.items()}
    flow_len = np.full((height, width), np.nan)
    rows, cols = np.nonzero(catch)
    for i in np.argsort(-acc_km2[rows, cols], kind="stable"):
        r, c = rows[i], cols[i]
        nxt = next_cell(r, c)
        flow_len[r, c] = 0.0 if nxt is None else flow_len[nxt] + step[int(fd[r, c])]

    # --- control points: dedupe (prefer villages), then link each to the next one downstream ---
    for cp in controls:
        cp["cell"] = cell_of(cp)
        cp["area_km2"] = float(acc_km2[cp["cell"]])
    rank = {"outlet": 0, "village": 1, "confluence": 2}
    controls.sort(key=lambda cp: (rank[cp["kind"]], -cp["area_km2"]))
    kept = []
    for cp in controls:
        # same site: within 300 m with similar drainage, or a confluence within 1 km of a village/outlet
        # with nearly the same drainage (the named place is the more useful control point)
        dist = lambda k: np.hypot(k["x"] - cp["x"], k["y"] - cp["y"])
        similar = lambda k, tol: abs(k["area_km2"] - cp["area_km2"]) / max(cp["area_km2"], 1) < tol
        dup = next((k for k in kept if (dist(k) < 300 and similar(k, 0.10))
                    or (cp["kind"] == "confluence" and dist(k) < 1000 and similar(k, 0.05))), None)
        if dup:
            print(f"    drop {cp['name']} (same site as {dup['name']})")
        else:
            kept.append(cp)
    controls = sorted(kept, key=lambda cp: -cp["area_km2"])
    for i, cp in enumerate(controls, start=1):
        cp["id"] = i

    def link_downstream(controls):
        at = {cp["cell"]: cp["id"] for cp in controls}
        for cp in controls:
            cp["downstream"], cell = 0, next_cell(*cp["cell"])
            while cell is not None:
                if cell in at:
                    cp["downstream"] = at[cell]
                    break
                cell = next_cell(*cell)

    def label(controls):
        lab = np.zeros((height, width), dtype="int32")
        for cp in sorted(controls, key=lambda cp: -cp["area_km2"]):   # upstream ones overwrite
            # index mode: pysheds' coordinate mode silently returns empty masks for some cells
            r, c = cp["cell"]
            cm = np.asarray(g.catchment(x=c, y=r, fdir=fdir, xytype="index")).astype(bool)
            lab[cm & catch] = cp["id"]
        return lab

    link_downstream(controls)
    labels = label(controls)
    while True:   # merge the smallest too-small increment into its downstream neighbour, repeat
        own = {cp["id"]: (labels == cp["id"]).sum() * CELL_KM2 for cp in controls}
        limit = {"outlet": 0.0, "village": MIN_VILLAGE_KM2, "confluence": MIN_SUBBASIN_KM2}
        small = [cp for cp in controls if own[cp["id"]] < limit[cp["kind"]]]
        if not small:
            break
        cp = min(small, key=lambda cp: own[cp["id"]])
        print(f"    merge {cp['name']} ({own[cp['id']]:.1f} km2) into #{cp['downstream']}")
        labels[labels == cp["id"]] = cp["downstream"]
        controls.remove(cp)
        link_downstream(controls)

    # --- sub-basin + reach attributes for the HMS engine -----------------------------
    slope = np.degrees(np.arctan(np.hypot(*np.gradient(np.asarray(dem), config.GRID_RES_M))))
    dem_a = np.asarray(dem)
    by_id = {cp["id"]: cp for cp in controls}
    subbasins, sb_features = [], []
    for cp in controls:
        m = labels == cp["id"]
        r, c = cp["cell"]
        rel_len = np.where(m, flow_len - flow_len[r, c], np.nan)
        far = np.unravel_index(np.nanargmax(rel_len), rel_len.shape)
        z_out = float(dem_a[r, c])
        reach = None
        if cp["downstream"]:
            d = by_id[cp["downstream"]]
            length = float(flow_len[r, c] - flow_len[d["cell"]])
            reach = {"to": d["id"], "length_m": round(length, 1),
                     "slope": round(max((z_out - float(dem_a[d["cell"]])) / max(length, 1.0), 1e-4), 5)}
        sb = {
            "id": cp["id"], "name": cp["name"], "kind": cp["kind"],
            "area_km2": round(float(m.sum() * CELL_KM2), 3),
            "drainage_km2": round(cp["area_km2"], 3),
            "longest_flowpath_m": round(float(rel_len[far]), 1),
            "relief_m": round(float(dem_a[far]) - z_out, 1),
            "outlet_elev_m": round(z_out, 1),
            "mean_elev_m": round(float(dem_a[m].mean()), 1),
            "mean_slope_deg": round(float(slope[m].mean()), 2),
            "outlet_xy": [cp["x"], cp["y"]],
            "outlet_lonlat": list(_to_wgs.transform(cp["x"], cp["y"])),
            "reach": reach,
        }
        if cp["kind"] == "village":
            sb["village_lonlat"] = [cp["village_lon"], cp["village_lat"]]
        subbasins.append(sb)
        poly = _wgs(_polygonize(m, transform))
        sb_features.append({"type": "Feature", "geometry": sg.mapping(poly),
                            "properties": {k: v for k, v in sb.items() if k not in ("reach", "outlet_xy")}})

    # --- write ----------------------------------------------------------------------
    grid.write(INTERIM / "dem_cond.tif", np.asarray(dem, dtype="float32"), "float32", -9999)
    grid.write(INTERIM / "fdir.tif", fd.astype("int16"), "int16", 0)
    grid.write(INTERIM / "acc_km2.tif", acc_km2.astype("float32"), "float32")
    grid.write(INTERIM / "hand.tif", hand, "float32", -9999)
    grid.write(INTERIM / "catchment.tif", catch.astype("uint8"), "uint8", 0)
    grid.write(INTERIM / "subbasins.tif", labels, "int32", 0)

    _write_geojson("catchment.geojson", [{"type": "Feature", "properties": {
        "name": f"Ounila at {OUTLET[0]}", "area_km2": round(float(catch.sum() * CELL_KM2), 1)},
        "geometry": sg.mapping(_wgs(_polygonize(catch, transform)))}])
    _write_geojson("subbasins.geojson", sb_features)
    _write_geojson("control_points.geojson", [{"type": "Feature", "geometry": {
        "type": "Point", "coordinates": sb["outlet_lonlat"]}, "properties": {
        "id": sb["id"], "name": sb["name"], "kind": sb["kind"], "drainage_km2": sb["drainage_km2"]}}
        for sb in subbasins])

    net = g.extract_river_network(fdir, R(acc_km2 >= STREAM_KM2))
    stream_feats = []
    for f in net["features"]:
        line = sg.shape(f["geometry"])
        mid = line.interpolate(0.5, normalized=True)
        col, row = ~transform * (mid.x, mid.y)
        if 0 <= row < height and 0 <= col < width and catch[int(row), int(col)]:
            stream_feats.append({"type": "Feature", "geometry": sg.mapping(_wgs(line)),
                                 "properties": {"drainage_km2": round(float(acc_km2[int(row), int(col)]), 2)}})
    _write_geojson("streams.geojson", stream_feats)

    (INTERIM / "basin_model.json").write_text(json.dumps({
        "outlet": OUTLET[0], "catchment_km2": round(float(catch.sum() * CELL_KM2), 2),
        "crs": config.CRS_WORK, "subbasins": subbasins}, indent=1), encoding="utf8")
    print(f"  {len(subbasins)} sub-basins, {len(stream_feats)} stream segments -> {INTERIM}")


if __name__ == "__main__":
    run()
