"""Impact engine: buildings, people, roads, isolation and shelters for every 2D library scenario.

Usage: python -m pipeline.impact.engine        (after pipeline.impact.prep and the 2D library)

Thresholds
  Building hazard   HR = d (v + 0.5) + DF  (DEFRA/EA FD2320, 2006); DF urban: 0 if d <= 0.25 m else 1.
                    Classes: < 0.75 low, 0.75-1.25 moderate, 1.25-2.0 significant, >= 2.0 extreme.
  Structural risk   earthen (pise/adobe) houses: damage likely if d > 1 m or d.v > 1 m2/s; collapse possible
                    if d > 2 m or d.v > 3 m2/s (after Clausen & Clark 1990, stricter for adobe). Indicative.
  Vehicles          ARR 2019 (Book 6 ch. 7): small car unsafe if d > 0.3 m or d.v > 0.3 m2/s; large 4WD /
                    emergency vehicle unsafe if d > 0.5 m or d.v > 0.6 m2/s.
  People on foot    adult unsafe if d.v > 0.4 m2/s or d > 0.5 m (ARR 2019).
  Bridges           decks assumed above the flood unless the water under them exceeds 2.5 m (flagged).
d.v is approximated as max(0, max[d(v+0.5)] - 0.5 max d), because maxima can occur at different times.

Outputs data/runs/impact/: villages.json, scenario_<name>.json (per-building and per-segment arrays),
shelters.geojson, graph.json, summary.json
"""

import json

import geopandas as gpd
import networkx as nx
import numpy as np

from pipeline import config, grid
from pipeline.hydraulics.scenarios import OUT as HYD, library

PREP = config.INTERIM / "impact"
OUT = config.RUNS / "impact"
SNAP_H = 0.5
HR_BANDS = (0.75, 1.25, 2.0)
HR_NAMES = ("dry", "low", "moderate", "significant", "extreme")


def load_static():
    b = gpd.read_file(PREP / "buildings.gpkg")
    s = gpd.read_file(PREP / "roads.gpkg")
    p = gpd.read_file(PREP / "pois.gpkg")
    s["cell_list"] = [np.array(list(map(int, c.split(","))), dtype=np.int64) for c in s["cells"]]
    return b, s, p


def scenario_rasters(name):
    d = HYD / name
    r = {k: grid.read(d / f"{k}.tif") for k in ("hmax", "vmax", "hvmax", "t_arrival_01", "t_arrival_03", "duration_03")}
    snaps = np.load(d / "snaps.npz")["depth"].astype(np.float32)
    return r, snaps


def domain_index():
    act = np.load(HYD / "domain_active.npy")
    idx = -np.ones(act.size, dtype=np.int64)
    idx[np.flatnonzero(act)] = np.arange(act.sum())
    return idx                                                 # flat grid cell -> domain cell (or -1)


def building_metrics(b, r):
    hmax, hv, ta = r["hmax"], r["hvmax"], r["t_arrival_01"]
    n = len(b)
    depth, hvm, arr = np.zeros(n), np.zeros(n), np.full(n, -1.0)
    for i, (r0, r1, c0, c1) in enumerate(zip(b["r0"], b["r1"], b["c0"], b["c1"])):
        win = (slice(min(r0, r1), max(r0, r1) + 1), slice(min(c0, c1), max(c0, c1) + 1))
        depth[i] = hmax[win].max()
        hvm[i] = hv[win].max()
        t = ta[win]
        arr[i] = t[t >= 0].min() if (t >= 0).any() else -1.0
    affected = depth >= 0.1
    df = np.where(depth > 0.25, 1.0, 0.0)
    hr = np.where(affected, hvm + df, 0.0)
    hr_class = np.where(~affected, 0, 1 + np.searchsorted(HR_BANDS, hr, side="right"))
    dv = np.maximum(hvm - 0.5 * depth, 0.0)
    structural = np.where(affected & ((depth > 2) | (dv > 3)), 2, np.where(affected & ((depth > 1) | (dv > 1)), 1, 0))
    return {"depth": depth, "hr": hr, "hr_class": hr_class, "arrival_h": np.where(affected, arr, -1.0),
            "structural": structural}


def segment_metrics(s, r, snaps, didx):
    hmax, hv = r["hmax"].ravel(), r["hvmax"].ravel()
    n, k = len(s), snaps.shape[0]
    depth, dv = np.zeros(n), np.zeros(n)
    car = np.zeros((n, k), dtype=bool)
    wd = np.zeros((n, k), dtype=bool)
    for i, cells in enumerate(s["cell_list"]):
        d = hmax[cells]
        depth[i] = d.max()
        dv[i] = np.maximum(hv[cells] - 0.5 * d, 0).max()
        dom = didx[cells]
        dom = dom[dom >= 0]
        if len(dom) == 0 or depth[i] < 0.1:
            continue
        ds = snaps[:, dom].max(axis=1)                                     # depth along the segment in time
        wet = ds > 0.1
        car[i] = wet & ((ds > 0.3) | (dv[i] > 0.3))
        wd[i] = wet & ((ds > 0.5) | (dv[i] > 0.6))
    bridge = s["bridge"].values.astype(bool)
    car[bridge] &= (depth[bridge] > 2.5)[:, None]
    wd[bridge] &= (depth[bridge] > 2.5)[:, None]

    def interval(m):
        first = np.where(m.any(axis=1), m.argmax(axis=1) * SNAP_H, -1.0)
        last = np.where(m.any(axis=1), (m.shape[1] - 1 - m[:, ::-1].argmax(axis=1)) * SNAP_H + SNAP_H, -1.0)
        return first, last
    car_from, car_to = interval(car)
    wd_from, wd_to = interval(wd)
    status = np.where(wd.any(axis=1), 2, np.where(car.any(axis=1), 1, 0))       # 0 open, 1 cars unsafe, 2 closed
    return {"depth": depth, "dv": dv, "status": status, "car_from": car_from, "car_to": car_to,
            "closed_from": wd_from, "closed_to": wd_to, "_wd": wd}


def build_graph(s):
    g = nx.Graph()
    for i, row in enumerate(s.itertuples()):
        if row.mode == "vehicle":
            g.add_edge(row.u, row.v, seg=i, length=row.length_m)
    return g


def anchors(s, g):
    rn9 = s[(s["ref"].fillna("").str.contains("RN9")) & (s["mode"] == "vehicle")]
    return set(rn9["u"]).union(rn9["v"]) & set(g.nodes)


def village_nodes(p, s, g):
    nodes = np.array([tuple(map(float, n.split(","))) for n in g.nodes])
    names = list(g.nodes)
    out = {}
    for _, v in p[(p["kind"] == "place") & p["name"].notna()].iterrows():
        d = np.hypot(nodes[:, 0] - v.geometry.x, nodes[:, 1] - v.geometry.y)
        k = int(np.argmin(d))
        out[v["name"]] = {"node": names[k] if d[k] < 2000 else None, "dist_to_road_m": round(float(d[k]))}
    return out


def isolation(g, anc, vnodes, wd):
    """Per village: first/last half-hour without a 4WD route to the RN9."""
    k = wd.shape[1]
    iso = {v: [] for v in vnodes}
    for t in range(k):
        closed = set(np.flatnonzero(wd[:, t]))
        h = nx.Graph()
        h.add_nodes_from(g.nodes)
        h.add_edges_from((u, v) for u, v, a in g.edges(data=True) if a["seg"] not in closed)
        comp = {n: c for c, nodes in enumerate(nx.connected_components(h)) for n in nodes}
        good = {comp[a] for a in anc}
        for v, info in vnodes.items():
            if info["node"] is not None and comp[info["node"]] not in good:
                iso[v].append(t * SNAP_H)
    baseline = {v for v, ts in iso.items() if ts and ts[0] == 0.0}      # no road link to RN9 even when dry
    return {v: ({"from_h": ts[0], "to_h": ts[-1] + SNAP_H, "hours": len(ts) * SNAP_H} if ts and v not in baseline else None)
            for v, ts in iso.items()}, baseline


def shelters(b, p, worst):
    """Facilities that stay dry in the largest library scenario; residents walk/drive there."""
    cand = b[b["type"].isin(["school", "mosque", "public"]) & (worst["depth"][b.index] < 0.05)]
    out = []
    for _, row in cand.iterrows():
        c = row.geometry.centroid
        out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [c.x, c.y]},
                    "properties": {"kind": row["type"],
                                   "name": row["facility_name"] if isinstance(row["facility_name"], str) else None,
                                   "village": row["village"],
                                   "source": "OSM facility, dry in the largest library scenario"}})
    return out


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    b, s, p = load_static()
    didx = domain_index()
    g = build_graph(s)
    anc = anchors(s, g)
    vnodes = village_nodes(p, s, g)
    lib = library()
    summary, villages = {}, {}
    worst = None
    for name, p24 in lib.items():
        if not (HYD / name / "run.json").exists():
            print(f"  {name}: no 2D run, skipped")
            continue
        r, snaps = scenario_rasters(name)
        bm = building_metrics(b, r)
        sm = segment_metrics(s, r, snaps, didx)
        iso, unreachable = isolation(g, anc, vnodes, sm["_wd"])
        aff = bm["depth"] >= 0.1
        vtab = {}
        for v, grp in b.groupby("village"):
            ix = grp.index.values
            a = aff[ix]
            vtab[v] = {
                "buildings": int(len(ix)), "buildings_affected": int(a.sum()),
                "by_hazard": {HR_NAMES[c]: int((bm["hr_class"][ix] == c).sum()) for c in range(1, 5)},
                "structural_damage_likely": int((bm["structural"][ix] >= 1).sum()),
                "collapse_possible": int((bm["structural"][ix] == 2).sum()),
                "people_affected": round(float(b["pop"].values[ix][a].sum()), 1),
                "facilities_affected": {t: int(((b["type"].values[ix] == t) & a).sum()) for t in ("school", "mosque", "health", "public", "tourism")},
                "first_water_h": round(float(bm["arrival_h"][ix][a].min()), 2) if a.any() else None,
                "isolation": iso.get(v),
            }
        villages[name] = vtab
        summary[name] = {
            "p24_mm": p24, "buildings_affected": int(aff.sum()), "people_affected": round(float(b["pop"].values[aff].sum())),
            "by_hazard": {HR_NAMES[c]: int((bm["hr_class"] == c).sum()) for c in range(1, 5)},
            "structural_damage_likely": int((bm["structural"] >= 1).sum()), "collapse_possible": int((bm["structural"] == 2).sum()),
            "facilities_affected": {t: int(((b["type"] == t).values & aff).sum()) for t in ("school", "mosque", "health", "public", "tourism")},
            "road_km_cars_unsafe": round(float(s["length_m"].values[sm["status"] >= 1].sum() / 1000), 1),
            "road_km_closed": round(float(s["length_m"].values[sm["status"] == 2].sum() / 1000), 1),
            "fords_closed": int(((sm["status"] == 2) & s["ford"].values.astype(bool)).sum()),
            "villages_isolated": sorted(v for v, x in iso.items() if x),
        }
        (OUT / f"scenario_{name}.json").write_text(json.dumps({
            "name": name, "p24_mm": p24,
            "buildings": {"depth": np.round(bm["depth"], 2).tolist(), "hr_class": bm["hr_class"].tolist(),
                          "arrival_h": np.round(bm["arrival_h"], 2).tolist(), "structural": bm["structural"].tolist()},
            "segments": {k: (np.round(v, 2).tolist() if v.dtype.kind == "f" else v.tolist())
                         for k, v in sm.items() if not k.startswith("_")},
        }), encoding="utf8")
        worst = bm
        ss = summary[name]
        print(f"  {name:5s} {p24:6.1f} mm | buildings {ss['buildings_affected']:5d} (extreme {ss['by_hazard']['extreme']:4d}) | "
              f"people {ss['people_affected']:5d} | collapse-possible {ss['collapse_possible']:4d} | closed roads "
              f"{ss['road_km_closed']:5.1f} km, fords {ss['fords_closed']:3d} | isolated {len(ss['villages_isolated'])}")
    (OUT / "villages.json").write_text(json.dumps(villages, ensure_ascii=False), encoding="utf8")
    (OUT / "summary.json").write_text(json.dumps({"scenarios": summary, "unreachable_by_road": sorted(unreachable),
                                                  "anchor_road": "RN9", "village_road_nodes": vnodes}, ensure_ascii=False, indent=1), encoding="utf8")
    (OUT / "shelters.geojson").write_text(json.dumps({"type": "FeatureCollection", "crs_epsg": 32629,
                                                      "features": shelters(b, p, worst)}, ensure_ascii=False), encoding="utf8")
    print(f"  anchors (RN9 nodes) {len(anc)}, villages with road node {sum(1 for v in vnodes.values() if v['node'])}/{len(vnodes)}, "
          f"never connected to RN9 even when dry: {len(unreachable)}")


if __name__ == "__main__":
    run()
