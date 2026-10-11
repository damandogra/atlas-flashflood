"""Static exposure layers for the impact engine. Usage: python -m pipeline.impact.prep

buildings  Google/VIDA footprints + residents (catchment total from GHS-POP/WorldPop spread over
           residential footprints by area) + type (OSM facility within 30 m) + village (nearest OSM
           place within 3 km) + the model-grid cells each footprint touches.
roads      OSM ways split at junctions into segments; vehicle vs foot mode; fords/bridges; sample cells
           every 15 m for flood sampling; graph nodes at segment ends.
pois       schools, mosques, tourism, administration, fords (points, UTM).
Output: data/interim/impact/{buildings.gpkg, roads.gpkg, pois.gpkg, prep.json}
"""

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import shapely.geometry as sg

from pipeline import config, grid

OUT = config.INTERIM / "impact"
VEHICLE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service",
           "track", "living_street", "road"}
FOOT = {"path", "footway", "steps", "pedestrian", "bridleway"}
FACILITY_KIND = [   # (tag, value regex, kind)
    ("amenity", r"^(school|kindergarten|college)$", "school"), ("building", r"^school$", "school"),
    ("amenity", r"^(clinic|doctors|hospital|pharmacy)$", "health"), ("healthcare", r".", "health"),
    ("amenity", r"^place_of_worship$", "mosque"), ("building", r"^mosque$", "mosque"),
    ("amenity", r"^(townhall|police|fire_station|community_centre)$", "public"),
    ("building", r"^(public|government)$", "public"),
    ("tourism", r"^(hotel|guest_house|hostel|camp_site)$", "tourism"),
]
SAMPLE_M = 15.0


def _utm(gdf):
    return gdf.set_crs(config.CRS_WEB, allow_override=True).to_crs(config.CRS_WORK)


def pois():
    g = _utm(gpd.read_file(config.RAW / "osm_pois_all.geojson"))
    g["kind"] = None
    for tag, rx, kind in FACILITY_KIND:
        if tag in g:
            m = g[tag].astype(str).str.match(rx) & g["kind"].isna() & g[tag].notna()
            g.loc[m, "kind"] = kind
    if "ford" in g:
        g.loc[g["ford"].notna() & g["kind"].isna(), "kind"] = "ford"
    if "place" in g:
        g.loc[g["place"].isin(["town", "village", "hamlet"]) & g["kind"].isna(), "kind"] = "place"
    g = g[g["kind"].notna()].copy()
    # display name: French (Latin script) where OSM has it, else the first Latin part of `name`
    g["name_local"] = g["name"]
    latin = g["name"].fillna("").str.extract(r"^([^ⴰ-⵿؀-ۿ]+)")[0].str.strip()
    g["name"] = (g["name:fr"] if "name:fr" in g else latin).fillna(latin).replace("", np.nan)
    # unique place names (a few hamlets share a name): suffix with the OSM id
    dup = (g["kind"] == "place") & g["name"].notna() & g.duplicated("name", keep=False)
    g.loc[dup, "name"] = g.loc[dup, "name"] + " (" + g.loc[dup, "osm_id"].astype(str) + ")"
    g["geometry"] = g.geometry.representative_point()
    keep = [c for c in ("osm_id", "kind", "name", "name_local", "name:ar", "amenity", "tourism", "place", "ford") if c in g]
    return g[keep + ["geometry"]].reset_index(drop=True)


def buildings(pois_g):
    b = _utm(gpd.read_file(config.RAW / "buildings_vida.geojson"))
    b["area_m2"] = b.geometry.area
    cent = b.geometry.centroid
    t, w, h = grid.model_grid()
    catch = grid.read(config.INTERIM / "catchment.tif").astype(bool)
    col, row = ~t * (cent.x.values, cent.y.values)
    b["in_catchment"] = catch[np.clip(row.astype(int), 0, h - 1), np.clip(col.astype(int), 0, w - 1)]

    # type from OSM facilities within 30 m, village from the nearest place within 3 km
    fac = pois_g[pois_g["kind"].isin(["school", "health", "mosque", "public", "tourism"])]
    j = gpd.sjoin_nearest(gpd.GeoDataFrame(geometry=cent, crs=b.crs), fac[["kind", "name", "geometry"]],
                          max_distance=30, how="left")
    j = j[~j.index.duplicated()]
    b["type"] = j["kind"].fillna("residential").values
    b["facility_name"] = j["name"].values
    places = pois_g[(pois_g["kind"] == "place") & pois_g["name"].notna()]
    jv = gpd.sjoin_nearest(gpd.GeoDataFrame(geometry=cent, crs=b.crs), places[["name", "geometry"]],
                           max_distance=3000, how="left", distance_col="d")
    jv = jv[~jv.index.duplicated()]
    b["village"] = jv["name"].fillna("Outlying buildings").values

    # residents, top-down dasymetric: catchment total (mean of GHS-POP 2020 and WorldPop 2020, which
    # agree within 5 %) spread over residential footprints by area. Neither 100 m product locates people
    # in these hamlets: GHS-POP lumps them into ~240 cells, unconstrained WorldPop smears them over
    # empty slopes. Non-residential buildings carry no residents (they are flagged by type instead).
    totals = json.loads((config.RAW / "population_totals.json").read_text(encoding="utf8"))
    res_area = b.loc[(b["type"] == "residential") & b["in_catchment"], "area_m2"].sum()
    density = totals["catchment_population"] / res_area
    b["pop"] = np.where(b["type"] == "residential", b["area_m2"] * density, 0.0)

    # model-grid cells touched by each footprint (for max-depth sampling)
    bounds = b.geometry.bounds.values
    c0, r1 = ~t * (bounds[:, 0], bounds[:, 1])
    c1, r0 = ~t * (bounds[:, 2], bounds[:, 3])
    b["r0"], b["r1"] = np.floor(r0).astype(int), np.floor(r1).astype(int)
    b["c0"], b["c1"] = np.floor(c0).astype(int), np.floor(c1).astype(int)
    return b.drop(columns=[c for c in ("bf_source",) if c in b])


def roads(pois_g):
    r = _utm(gpd.read_file(config.RAW / "osm_roads_all.geojson"))
    r = r[r["highway"].isin(VEHICLE | FOOT)].reset_index(drop=True)
    # split ways at vertices shared with other ways (junctions)
    coords = [np.round(np.asarray(g.coords), 1) for g in r.geometry]
    seen = pd.Series([tuple(p) for cs in coords for p in cs]).value_counts()
    junction = set(seen[seen > 1].index)
    fords = shapely.STRtree(pois_g[pois_g["kind"] == "ford"].geometry.values)
    segs = []
    for i, cs in enumerate(coords):
        props = r.iloc[i]
        start = 0
        for k in range(1, len(cs)):
            if tuple(cs[k]) in junction or k == len(cs) - 1:
                if k > start:
                    line = sg.LineString(cs[start:k + 1])
                    segs.append({"way": int(props.get("osm_id", i)), "highway": props["highway"],
                                 "ref": props.get("ref"), "name": props.get("name"),
                                 "mode": "vehicle" if props["highway"] in VEHICLE else "foot",
                                 "bridge": props.get("bridge") not in (None, "no") and pd.notna(props.get("bridge")),
                                 "ford_tag": pd.notna(props.get("ford")) and props.get("ford") != "no",
                                 "u": tuple(cs[start]), "v": tuple(cs[k]), "geometry": line})
                start = k
    s = gpd.GeoDataFrame(segs, crs=config.CRS_WORK)
    s["length_m"] = s.geometry.length
    near_ford = fords.query(s.geometry.values, predicate="dwithin", distance=20)
    s["ford"] = s["ford_tag"]
    s.loc[np.unique(near_ford[0]), "ford"] = True
    t, w, h = grid.model_grid()
    cells = []
    for g in s.geometry:
        n = max(int(g.length // SAMPLE_M), 1)
        pts = [g.interpolate(d) for d in np.linspace(0, g.length, n + 1)]
        col, row = ~t * (np.array([p.x for p in pts]), np.array([p.y for p in pts]))
        idx = np.unique(np.clip(row.astype(int), 0, h - 1) * w + np.clip(col.astype(int), 0, w - 1))
        cells.append(idx)
    s["cells"] = [",".join(map(str, c)) for c in cells]
    s["u"] = s["u"].map(lambda p: f"{p[0]:.1f},{p[1]:.1f}")
    s["v"] = s["v"].map(lambda p: f"{p[0]:.1f},{p[1]:.1f}")
    s["seg_id"] = np.arange(len(s))
    return s.drop(columns=["ford_tag"])


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    p = pois()
    b = buildings(p)
    s = roads(p)
    p.to_file(OUT / "pois.gpkg")
    b.to_file(OUT / "buildings.gpkg")
    s.to_file(OUT / "roads.gpkg")
    info = {
        "buildings": int(len(b)), "buildings_in_catchment": int(b["in_catchment"].sum()),
        "population_in_buildings": round(float(b["pop"].sum())),
        "population_catchment": round(float(b.loc[b["in_catchment"], "pop"].sum())),
        "residents_per_100m2_footprint": round(float(b.loc[b["pop"] > 0, "pop"].sum() / b.loc[b["pop"] > 0, "area_m2"].sum() * 100), 3),
        "building_types": b["type"].value_counts().to_dict(),
        "road_segments": int(len(s)), "road_km": round(float(s["length_m"].sum() / 1000), 1),
        "road_km_by_mode": (s.groupby("mode")["length_m"].sum() / 1000).round(1).to_dict(),
        "ford_segments": int(s["ford"].sum()), "bridge_segments": int(s["bridge"].sum()),
        "pois": p["kind"].value_counts().to_dict(),
    }
    (OUT / "prep.json").write_text(json.dumps(info, indent=1), encoding="utf8")
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    run()
