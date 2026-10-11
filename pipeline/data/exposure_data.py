"""Exposure data for the impact engine. Usage: python -m pipeline.data.exposure_data [buildings|osm|worldpop|all]

buildings  Google Open Buildings footprints via the VIDA combined dataset (Earth Engine community
           catalogue, projects/sat-io/open-datasets/VIDA_COMBINED/MAR), confidence >= 0.65.
           OSM maps < 3 % of the buildings here; Google v3 itself is not served for Morocco in EE.
osm        Roads and tracks (all highway classes), fords and bridges, schools, health, mosques,
           administration, tourism, places - Overpass, catchment + downstream extension.
worldpop   WorldPop 2020 unconstrained 100 m counts (kept for reference: it smears people over empty slopes).
population Catchment total from GHS-POP 2020 and WorldPop 2020 (they agree within 5 %), used top-down.
"""

import json
import sys
import time

import ee
import numpy as np
import rasterio
import requests
import shapely.geometry as sg

from pipeline import config
from pipeline.data.download import UA

RAW = config.RAW
MIN_CONFIDENCE = 0.65
BUFFER_M = 3000


def _area():
    c = json.loads((config.INTERIM / "catchment.geojson").read_text(encoding="utf8"))["features"][0]["geometry"]
    shp = sg.shape(c)
    lon0, lat0, lon1, lat1 = shp.bounds
    return c, (lon0 - 0.04, lat0 - 0.05, lon1 + 0.04, lat1 + 0.03)   # + the 2 km extension below the outlet


def buildings():
    c, bbox = _area()
    region = ee.Geometry(c).buffer(BUFFER_M).union(ee.Geometry.Rectangle(list(bbox)).intersection(
        ee.Geometry.Point([-7.131, 31.045]).buffer(4000)))
    fc = (ee.FeatureCollection("projects/sat-io/open-datasets/VIDA_COMBINED/MAR").filterBounds(region)
          .filter(ee.Filter.gte("confidence", MIN_CONFIDENCE)).select(["area_in_meters", "confidence", "bf_source"]))
    feats = []
    n = fc.size().getInfo()
    lst = fc.toList(n)
    for i in range(0, n, 4000):                         # page through (getInfo limit)
        chunk = ee.FeatureCollection(lst.slice(i, i + 4000)).getInfo()["features"]
        feats += chunk
    for k, f in enumerate(feats):
        f["properties"]["bid"] = k
        f.pop("id", None)
    path = RAW / "buildings_vida.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf8")
    print(f"  buildings: {len(feats)} footprints (confidence >= {MIN_CONFIDENCE}) -> {path}")


OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]

OSM_QUERY = """[out:json][timeout:180];
(
  way["highway"]({b});
  node["ford"]({b}); way["ford"]({b}); way["bridge"]({b});
  node["amenity"~"school|kindergarten|college|clinic|doctors|hospital|pharmacy|place_of_worship|townhall|police|fire_station|community_centre|marketplace|fuel"]({b});
  way["amenity"~"school|kindergarten|college|clinic|doctors|hospital|pharmacy|place_of_worship|townhall|police|fire_station|community_centre|marketplace|fuel"]({b});
  node["healthcare"]({b}); way["healthcare"]({b});
  node["tourism"~"hotel|guest_house|hostel|camp_site|attraction|museum"]({b});
  way["tourism"~"hotel|guest_house|hostel|camp_site|attraction|museum"]({b});
  way["building"~"school|mosque|hospital|public|government"]({b});
  node["place"~"town|village|hamlet"]({b});
);
out geom;"""


def osm():
    _, (lon0, lat0, lon1, lat1) = _area()
    q = OSM_QUERY.replace("{b}", f"{lat0},{lon0},{lat1},{lon1}")
    for attempt, url in enumerate(OVERPASS * 2):                  # public mirrors time out under load
        try:
            r = requests.post(url, data={"data": q}, headers=UA, timeout=300)
            r.raise_for_status()
            break
        except requests.RequestException as e:
            print(f"    {url}: {e}")
            time.sleep(15 * (attempt + 1))
    else:
        raise RuntimeError("all Overpass endpoints failed")
    roads, pois = [], []
    for e in r.json()["elements"]:
        tags = e.get("tags", {})
        if e["type"] == "node":
            geom = {"type": "Point", "coordinates": [e["lon"], e["lat"]]}
        elif "geometry" in e:
            pts = [[p["lon"], p["lat"]] for p in e["geometry"]]
            closed = len(pts) > 3 and pts[0] == pts[-1]
            geom = {"type": "Polygon", "coordinates": [pts]} if closed and "highway" not in tags else \
                   {"type": "LineString", "coordinates": pts}
        else:
            continue
        feat = {"type": "Feature", "geometry": geom, "properties": {"osm_id": e["id"], "osm_type": e["type"], **tags}}
        (roads if "highway" in tags and geom["type"] == "LineString" else pois).append(feat)
    for name, feats in (("osm_roads_all.geojson", roads), ("osm_pois_all.geojson", pois)):
        (RAW / name).write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False),
                                encoding="utf8")
    print(f"  osm: {len(roads)} road/track ways, {len(pois)} facilities/fords/places")


def worldpop():
    _, (lon0, lat0, lon1, lat1) = _area()
    img = (ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "MAR"))
           .filter(ee.Filter.eq("year", 2020)).first().select("population"))
    proj = img.projection().getInfo()
    url = img.getDownloadURL({"region": ee.Geometry.Rectangle([lon0, lat0, lon1, lat1]), "crs": proj["crs"],
                              "crs_transform": proj["transform"], "format": "GEO_TIFF"})
    path = RAW / "worldpop2020_100m.tif"
    path.write_bytes(requests.get(url, timeout=300).content)
    with rasterio.open(path) as src:
        a = src.read(1)
    print(f"  worldpop: {np.nansum(np.where(a > 0, a, 0)):.0f} people in the bbox -> {path}")


def population_totals():
    """Catchment population from two independent gridded products (both 2020, 100 m)."""
    c, _ = _area()
    g = ee.Geometry(c)
    ghs = ee.ImageCollection("JRC/GHSL/P2023A/GHS_POP").filter(ee.Filter.calendarRange(2020, 2020, "year")).first()
    wp = (ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "MAR"))
          .filter(ee.Filter.eq("year", 2020)).first())
    tot = {"ghs_pop_2020": ghs.reduceRegion(ee.Reducer.sum(), g, 100, maxPixels=1e9).getInfo()["population_count"],
           "worldpop_2020": wp.reduceRegion(ee.Reducer.sum(), g, 100, maxPixels=1e9).getInfo()["population"]}
    tot["catchment_population"] = round((tot["ghs_pop_2020"] + tot["worldpop_2020"]) / 2)
    (RAW / "population_totals.json").write_text(json.dumps(tot, indent=1), encoding="utf8")
    print(f"  population: {tot}")


STEPS = {"buildings": buildings, "osm": osm, "worldpop": worldpop, "population": population_totals}

if __name__ == "__main__":
    wanted = sys.argv[1:] or ["all"]
    ee.Initialize(project=config.EE_PROJECT)
    for name, fn in STEPS.items():
        if "all" in wanted or name in wanted:
            print(f"[exposure] {name}")
            fn()
