"""
02_analyse_exposure.py
======================
Issue #13 / #14 — Building-level flood exposure analysis.

For every building in OSM, samples depth and velocity from Person A's rasters,
applies the HR Wallingford hazard formula, weights by building vulnerability,
and writes one GeoJSON per scenario to data/outputs/.

Also writes exposure_summary.json with aggregate stats for the API.

Usage:
    python 02_analyse_exposure.py
"""

import os
import sys
import json
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.crs import CRS
from shapely.geometry import mapping

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vuln_weight(row: dict) -> float:
    """Return vulnerability weight for a building row based on OSM tags."""
    amenity = str(row.get("amenity", "")).lower()
    building = str(row.get("building", "")).lower()

    if amenity in ("hospital", "clinic"):
        return config.VULN_WEIGHTS["hospital"]
    if amenity == "school":
        return config.VULN_WEIGHTS["school"]
    if amenity == "fire_station":
        return config.VULN_WEIGHTS["fire_station"]
    if building in ("residential", "house", "apartments"):
        return config.VULN_WEIGHTS["residential"]
    if building in ("commercial", "retail", "office"):
        return config.VULN_WEIGHTS["commercial"]
    return config.VULN_WEIGHTS["default"]


def _classify_risk(score: float) -> str:
    if score > config.PARAMS["risk_levels"]["high"]:
        return "High"
    if score > config.PARAMS["risk_levels"]["medium"]:
        return "Medium"
    return "Low"


def _sample_raster(src: rasterio.DatasetReader, centroids: list) -> np.ndarray:
    """Sample raster values at a list of (x, y) centroid tuples.
    Returns nodata as NaN."""
    nodata = src.nodata
    values = np.array([v[0] for v in src.sample(centroids)], dtype=float)
    if nodata is not None:
        values[values == nodata] = np.nan
    values = np.where(values < 0, np.nan, values)   # negative = nodata guard
    return values


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze_exposure() -> dict:
    """
    Run exposure analysis for all available scenarios.

    Returns a summary dict (also written to data/outputs/exposure_summary.json).
    """
    buildings_path = os.path.join(config.DATA_RAW, config.LAYERS["buildings"])
    pois_path      = os.path.join(config.DATA_RAW, config.LAYERS["pois"])

    if not os.path.exists(buildings_path):
        print(f"❌  Buildings file not found: {buildings_path}")
        print("    Run 01_download_osm.py first.")
        return {}

    # ------------------------------------------------------------------
    # Load buildings + merge POIs so hospitals etc. carry amenity tags
    # ------------------------------------------------------------------
    print("   📦 Loading buildings …")
    buildings = gpd.read_file(buildings_path)

    # Keep only polygon/multipolygon geometries (drop nodes/lines)
    buildings = buildings[buildings.geometry.geom_type.isin(
        ["Polygon", "MultiPolygon"]
    )].copy()

    if os.path.exists(pois_path):
        pois = gpd.read_file(pois_path)
        # Spatial join: attach amenity from nearby POI to building if within 50 m
        pois_proj = pois[["amenity", "geometry"]].to_crs(config.PROJ_CRS)
        pois_proj["geometry"] = pois_proj.geometry.buffer(50)
        buildings_proj = buildings.to_crs(config.PROJ_CRS)
        joined = gpd.sjoin(
            buildings_proj, pois_proj[["amenity", "geometry"]],
            how="left", predicate="intersects"
        )
        # Prefer existing amenity tag; fall back to joined POI
        if "amenity_left" in joined.columns:
            joined["amenity"] = joined["amenity_left"].fillna(joined.get("amenity_right", ""))
        buildings = joined.drop(columns=[c for c in joined.columns
                                         if c.endswith("_left") or c.endswith("_right")
                                         or c == "index_right"], errors="ignore")
        buildings = buildings.to_crs(config.GEO_CRS)

    # Reproject to UTM for metric operations
    buildings_proj = buildings.to_crs(config.PROJ_CRS)

    # Pre-compute centroids in UTM, then convert to WGS84 for raster sampling
    # (rasters from Person A are expected in EPSG:4326 or 32629 — we handle both)
    centroids_proj = [(g.centroid.x, g.centroid.y)
                      for g in buildings_proj.geometry]

    # Pre-compute vulnerability weights (row-wise, using .itertuples is slow;
    # use apply on a dict representation)
    buildings_proj["vuln_weight"] = [
        _vuln_weight(row) for row in buildings_proj.to_dict("records")
    ]

    summary = {}

    # ------------------------------------------------------------------
    # Per-scenario loop
    # ------------------------------------------------------------------
    for ts, info in config.SCENARIOS.items():
        depth_path = os.path.join(config.DATA_TIF, info["depth"])
        vel_path   = os.path.join(config.DATA_TIF, info["vel"])

        if not os.path.exists(depth_path):
            print(f"   ⏩  Skipping {ts}: depth raster not found ({depth_path})")
            continue
        if not os.path.exists(vel_path):
            print(f"   ⏩  Skipping {ts}: velocity raster not found ({vel_path})")
            continue

        print(f"   🌊  Processing {info['label']} …")
        gdf = buildings_proj.copy()

        # --- Sample rasters ---
        # Detect raster CRS and reproject centroids if needed
        with rasterio.open(depth_path) as d_src:
            raster_crs = d_src.crs
            if raster_crs and raster_crs != CRS.from_epsg(32629):
                # Raster is in geographic CRS → reproject centroids to match
                import pyproj
                transformer = pyproj.Transformer.from_crs(
                    config.PROJ_CRS, raster_crs.to_epsg() or "EPSG:4326",
                    always_xy=True
                )
                sample_pts = [transformer.transform(x, y) for x, y in centroids_proj]
            else:
                sample_pts = centroids_proj

            gdf["depth_m"] = _sample_raster(d_src, sample_pts)

        with rasterio.open(vel_path) as v_src:
            gdf["velocity_ms"] = _sample_raster(v_src, sample_pts)

        # Fill NaN (outside raster extent = no flood)
        gdf["depth_m"]     = gdf["depth_m"].fillna(0.0)
        gdf["velocity_ms"] = gdf["velocity_ms"].fillna(0.0)

        # --- HR Wallingford hazard formula ---
        # HR = depth × (velocity + 0.5) + debris_factor
        gdf["hazard_score"] = (
            gdf["depth_m"] * (gdf["velocity_ms"] + 0.5)
            + config.PARAMS["debris_factor"]
        )

        # --- Weighted risk score ---
        gdf["risk_score"] = gdf["hazard_score"] * gdf["vuln_weight"]
        gdf["risk_level"] = gdf["risk_score"].apply(_classify_risk)

        # --- Filter to flooded buildings only ---
        flooded = gdf[gdf["depth_m"] >= config.PARAMS["flood_min_m"]].copy()

        # --- Identify critical assets at risk ---
        flooded["is_critical"] = flooded["vuln_weight"] >= 2.5

        # --- Output ---
        out_gdf = flooded.to_crs(config.GEO_CRS)

        # Drop geometry columns that can't serialise (MultiIndex from osmnx)
        out_gdf = out_gdf.reset_index(drop=True)

        # Keep useful columns only
        keep = [c for c in ["geometry", "osmid", "building", "amenity", "name",
                             "depth_m", "velocity_ms", "hazard_score",
                             "vuln_weight", "risk_score", "risk_level",
                             "is_critical"]
                if c in out_gdf.columns]
        out_gdf = out_gdf[keep]

        out_path = os.path.join(config.DATA_OUT, f"exposure_{ts}.geojson")
        out_gdf.to_file(out_path, driver="GeoJSON")

        # --- Summary stats for this scenario ---
        n_flooded  = len(flooded)
        n_critical = int(flooded["is_critical"].sum())
        n_high     = int((flooded["risk_level"] == "High").sum())
        n_medium   = int((flooded["risk_level"] == "Medium").sum())

        summary[ts] = {
            "label":             info["label"],
            "buildings_flooded": n_flooded,
            "critical_at_risk":  n_critical,
            "high_risk":         n_high,
            "medium_risk":       n_medium,
            "low_risk":          n_flooded - n_high - n_medium,
            "max_depth_m":       round(float(flooded["depth_m"].max()), 2) if n_flooded else 0,
            "max_hazard_score":  round(float(flooded["hazard_score"].max()), 2) if n_flooded else 0,
        }

        print(f"      ✅  {n_flooded} buildings flooded | "
              f"{n_critical} critical assets | {n_high} high-risk")
        print(f"          Saved → {out_path}")

    # ------------------------------------------------------------------
    # Write summary JSON (consumed by API /exposure endpoint)
    # ------------------------------------------------------------------
    summary_path = os.path.join(config.DATA_OUT, "exposure_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n   📊  Summary → {summary_path}")

    return summary


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("🌊  EXPOSURE ANALYSIS  (Issues #13 / #14)")
    print("=" * 55)
    result = analyze_exposure()
    if result:
        print("\nScenario summary:")
        for ts, s in result.items():
            print(f"  {ts}: {s['buildings_flooded']} flooded, "
                  f"{s['critical_at_risk']} critical, "
                  f"max depth {s['max_depth_m']} m")