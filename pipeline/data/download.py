"""Phase 1 downloads. Usage: python -m pipeline.data.download [dem|landcover|soil|places|rain|imerg|all]

`rain` and `imerg` need the catchment from pipeline.data.terrain, so run them after terrain.

Rasters come from Google Earth Engine and are warped onto the shared model grid (pipeline.grid).
"""

import json
import sys
import time

import ee
import numpy as np
import requests
import rasterio
from rasterio.warp import Resampling, reproject

from pipeline import config, grid

RAW = config.RAW
UA = {"User-Agent": "Atlas-flood-DSS/2.0 (MSc Geomatics research prototype)"}


# --- Earth Engine rasters ------------------------------------------------------

def _ee_download(image, name, resampling, dtype, nodata=None, tiles=1):
    """Download an EE image over the model grid in tiles x tiles blocks and mosaic it onto the grid.

    Tiling keeps each request under Earth Engine's size limits (needed when aggregating 10 m data).
    """
    transform, width, height = grid.model_grid()
    r = config.GRID_RES_M
    fill = nodata if nodata is not None else 0
    mosaic = np.full((height, width), fill, dtype=dtype)
    col_edges = np.linspace(0, width, tiles + 1).astype(int)
    row_edges = np.linspace(0, height, tiles + 1).astype(int)
    tmp = RAW / f"{name}_ee.tif"
    for r0, r1 in zip(row_edges[:-1], row_edges[1:]):
        for c0, c1 in zip(col_edges[:-1], col_edges[1:]):
            x0, y0 = transform.c + c0 * r, transform.f - r0 * r
            region = ee.Geometry.Rectangle([x0, y0 - (r1 - r0) * r, x0 + (c1 - c0) * r, y0],
                                           proj=config.CRS_WORK, geodesic=False)
            url = image.getDownloadURL({"region": region, "crs": config.CRS_WORK,
                                        "crs_transform": [r, 0, x0, 0, -r, y0], "format": "GEO_TIFF"})
            with requests.get(url, stream=True, timeout=600) as resp:
                if not resp.ok:
                    raise RuntimeError(f"Earth Engine download of {name} failed ({resp.status_code}): {resp.text[:300]}")
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(1 << 20):
                        f.write(chunk)
            block = np.full((height, width), fill, dtype=dtype)
            with rasterio.open(tmp) as src:
                reproject(rasterio.band(src, 1), block, dst_transform=transform, dst_crs=config.CRS_WORK,
                          dst_nodata=fill, resampling=resampling)
            mosaic[r0:r1, c0:c1] = block[r0:r1, c0:c1]
    tmp.unlink()
    out = grid.write(RAW / f"{name}.tif", mosaic, dtype, nodata)
    print(f"  {name}: {out}")


def dem():
    img = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic().toFloat()
    _ee_download(img, "dem", Resampling.bilinear, "float32", -9999.0)


def landcover():
    # ESA WorldCover v200 (2021, 10 m) -> majority class per 30 m cell
    # (reduceResolution aggregates onto the download's crs_transform; no explicit reproject)
    img = (ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
           .reduceResolution(ee.Reducer.mode(), maxPixels=64).toUint8())
    _ee_download(img, "worldcover", Resampling.nearest, "uint8", 0, tiles=3)


def soil():
    # OpenLandMap USDA texture class (250 m), topsoil (b0) and 30 cm (b30)
    img = ee.Image("OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02")
    _ee_download(img.select("b0").toUint8(), "soil_texture_b0", Resampling.nearest, "uint8", 0)
    _ee_download(img.select("b30").toUint8(), "soil_texture_b30", Resampling.nearest, "uint8", 0)


# --- OpenStreetMap places --------------------------------------------------------

def places():
    lon0, lat0, lon1, lat1 = config.AOI_BBOX
    q = f'[out:json][timeout:90];node["place"~"town|village|hamlet|locality"]({lat0},{lon0},{lat1},{lon1});out;'
    r = requests.post("https://overpass-api.de/api/interpreter", data={"data": q}, headers=UA, timeout=180)
    r.raise_for_status()
    feats = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [e["lon"], e["lat"]]},
        "properties": {
            "osm_id": e["id"], "place": e["tags"].get("place"),
            "name": e["tags"].get("name:fr") or e["tags"].get("name:en") or e["tags"].get("name"),
            "name_local": e["tags"].get("name"),
        },
    } for e in r.json()["elements"]]
    path = RAW / "osm_places.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf8")
    print(f"  places: {len(feats)} -> {path}")


# --- Rainfall: ERA5-Land hourly via Earth Engine ------------------------------------

RAIN_YEARS = range(1950, 2026)


def _rain_year(region, year):
    """Hourly total precipitation and snowfall (m w.e.) for every ERA5-Land cell (~0.1 deg) in region."""
    for attempt in range(4):
        try:
            rows = (ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
                    .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
                    .select(["total_precipitation_hourly", "snowfall_hourly"])
                    .getRegion(region, 11132).getInfo())
            return rows[1:]
        except ee.EEException as e:
            print(f"    {year}: retry after {e}")
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"ERA5-Land extraction failed for {year}")


def rain():
    """Needs data/interim/catchment.geojson (run pipeline.data.terrain first)."""
    import shapely.geometry as sg
    from concurrent.futures import ThreadPoolExecutor

    catchment = json.loads((config.INTERIM / "catchment.geojson").read_text(encoding="utf8"))
    b = sg.shape(catchment["features"][0]["geometry"]).bounds
    region = ee.Geometry.Rectangle([b[0] - 0.05, b[1] - 0.05, b[2] + 0.05, b[3] + 0.05])
    with ThreadPoolExecutor(max_workers=4) as pool:
        per_year = dict(zip(RAIN_YEARS, pool.map(lambda y: _rain_year(region, y), RAIN_YEARS)))

    pixels = sorted({(round(r[1], 4), round(r[2], 4)) for r in per_year[RAIN_YEARS[0]]})
    pix_index = {p: i for i, p in enumerate(pixels)}
    times = np.arange(np.datetime64(f"{RAIN_YEARS[0]}-01-01T00"), np.datetime64(f"{RAIN_YEARS[-1] + 1}-01-01T00"),
                      np.timedelta64(1, "h"))
    t0 = times[0].astype("datetime64[ms]").astype("int64")
    precip = np.full((len(pixels), len(times)), np.nan, dtype="float32")
    snow = np.full_like(precip, np.nan)
    for rows in per_year.values():
        for _, lon, lat, t_ms, tp, sf in rows:
            i, k = pix_index[(round(lon, 4), round(lat, 4))], (t_ms - t0) // 3_600_000
            if tp is not None:
                precip[i, k] = max(tp, 0.0) * 1000.0
            if sf is not None:
                snow[i, k] = max(sf, 0.0) * 1000.0
    np.savez_compressed(RAW / "era5land_hourly.npz", time=times, lonlat=np.array(pixels), precip_mm=precip, snow_mm=snow)
    print(f"  rain: {len(pixels)} ERA5-Land cells x {len(times)} hours, "
          f"{np.isnan(precip).mean() * 100:.2f}% missing -> {RAW / 'era5land_hourly.npz'}")


# --- Rainfall: GPM IMERG V07 half-hourly (sub-daily storm structure) -----------------

IMERG_YEARS = range(1998, 2026)


def _imerg_month(region, year, month):
    end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"
    for attempt in range(4):
        try:
            return (ee.ImageCollection("NASA/GPM_L3/IMERG_V07")
                    .filterDate(f"{year}-{month:02d}-01", end).select("precipitation")
                    .getRegion(region, 11132).getInfo())[1:]
        except ee.EEException as e:
            print(f"    {year}-{month:02d}: retry after {e}")
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"IMERG extraction failed for {year}-{month:02d}")


def imerg():
    """Half-hourly IMERG V07 Final (mm per 30 min) on the same ~0.1 deg cells as ERA5-Land.
    Needs data/interim/catchment.geojson."""
    import shapely.geometry as sg
    from concurrent.futures import ThreadPoolExecutor

    catchment = json.loads((config.INTERIM / "catchment.geojson").read_text(encoding="utf8"))
    b = sg.shape(catchment["features"][0]["geometry"]).bounds
    region = ee.Geometry.Rectangle([b[0] - 0.05, b[1] - 0.05, b[2] + 0.05, b[3] + 0.05])
    months = [(y, m) for y in IMERG_YEARS for m in range(1, 13)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        chunks = list(pool.map(lambda ym: _imerg_month(region, *ym), months))

    pixels = sorted({(round(r[1], 4), round(r[2], 4)) for r in chunks[0]})
    pix_index = {p: i for i, p in enumerate(pixels)}
    times = np.arange(np.datetime64(f"{IMERG_YEARS[0]}-01-01T00:00"), np.datetime64(f"{IMERG_YEARS[-1] + 1}-01-01T00:00"),
                      np.timedelta64(30, "m"))
    t0 = times[0].astype("datetime64[ms]").astype("int64")
    precip = np.full((len(pixels), len(times)), np.nan, dtype="float32")
    for rows in chunks:
        for _, lon, lat, t_ms, v in rows:
            if v is not None:
                precip[pix_index[(round(lon, 4), round(lat, 4))], (t_ms - t0) // 1_800_000] = max(v, 0.0) * 0.5  # mm/h -> mm/30 min
    np.savez_compressed(RAW / "imerg_halfhourly.npz", time=times, lonlat=np.array(pixels), precip_mm=precip)
    print(f"  imerg: {len(pixels)} cells x {len(times)} half-hours, "
          f"{np.isnan(precip).mean() * 100:.2f}% missing -> {RAW / 'imerg_halfhourly.npz'}")


STEPS = {"dem": dem, "landcover": landcover, "soil": soil, "places": places, "rain": rain, "imerg": imerg}

if __name__ == "__main__":
    wanted = sys.argv[1:] or ["all"]
    if any(w in ("dem", "landcover", "soil", "rain", "imerg", "all") for w in wanted):
        ee.Initialize(project=config.EE_PROJECT)
    for name, fn in STEPS.items():
        if "all" in wanted or name in wanted:
            print(f"[download] {name}")
            fn()
