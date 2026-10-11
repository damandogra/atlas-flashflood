"""
02_analyse_network.py
=====================
Issue #16 — Road passability and evacuation network analysis.

For each road segment:
  - Samples max flood depth from the depth raster
  - Classifies as: Green (passable) / Orange (emergency only) / Red (impassable)

Then runs network analysis using networkx to identify isolated communities
— villages or clusters that lose ALL road connections to the rest of the network.

Outputs:
  data/outputs/road_passability_T*.geojson  — edges with depth + status
  data/outputs/evacuation_summary.json      — isolation counts per scenario

Usage:
    python 02_analyse_network.py
"""

import os
import sys
import json
import warnings
import numpy as np
import geopandas as gpd
import networkx as nx
import rasterio
from rasterio.crs import CRS
from shapely.geometry import Point, mapping

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASSABLE_M   = config.PARAMS["road_passable_m"]    # < 0.3 m → green
EMERGENCY_M  = config.PARAMS["road_emergency_m"]   # < 0.6 m → orange


def _classify_road(depth_m: float) -> dict:
    if np.isnan(depth_m) or depth_m < PASSABLE_M:
        return {"status": "passable",          "color": "green",  "passable": True,  "emergency_ok": True}
    if depth_m < EMERGENCY_M:
        return {"status": "emergency_only",    "color": "orange", "passable": False, "emergency_ok": True}
    return     {"status": "impassable",        "color": "red",    "passable": False, "emergency_ok": False}


def _sample_max_depth_along_segment(geom, src, n_points: int = 10):
    """
    Sample depth raster at n_points equally spaced along a line geometry.
    Returns the maximum sampled depth (representing worst-case for that segment).
    """
    if geom is None or geom.is_empty:
        return 0.0
    length = geom.length
    if length == 0:
        pts = [geom.interpolate(0)]
    else:
        pts = [geom.interpolate(i / (n_points - 1), normalized=True)
               for i in range(n_points)]

    coords = [(p.x, p.y) for p in pts]
    try:
        depths = [v[0] for v in src.sample(coords)]
    except Exception:
        return 0.0

    nodata = src.nodata
    valid  = [d for d in depths
              if d is not None and not np.isnan(d)
              and (nodata is None or d != nodata)
              and d >= 0]
    return float(max(valid)) if valid else 0.0


def _load_roads(roads_path: str) -> gpd.GeoDataFrame:
    """Load OSM roads and project to UTM."""
    gdf = gpd.read_file(roads_path)
    # Keep only line geometries
    gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    gdf = gdf.reset_index(drop=True)
    return gdf.to_crs(config.PROJ_CRS)


def _build_graph(roads_gdf: gpd.GeoDataFrame,
                 status_col: str = "status") -> nx.Graph:
    """
    Build a simple undirected graph from road edges.
    Impassable edges are removed so connectivity reflects flood conditions.
    """
    G = nx.Graph()
    for idx, row in roads_gdf.iterrows():
        if row[status_col] == "impassable":
            continue   # severed — don't add to graph
        geom = row.geometry
        if geom.geom_type == "MultiLineString":
            geom = geom.geoms[0]
        start = (round(geom.coords[0][0],  0), round(geom.coords[0][1],  0))
        end   = (round(geom.coords[-1][0], 0), round(geom.coords[-1][1], 0))
        length = row.get("length", geom.length)
        G.add_edge(start, end, edge_id=idx, length=length)
    return G


def _find_isolated_communities(roads_gdf: gpd.GeoDataFrame,
                                status_col: str = "status") -> list:
    """
    Find groups of road nodes that are disconnected from the main network.
    Each isolated component (excluding the largest) is a potentially isolated community.

    Returns a list of dicts with centroid, node_count, edge_count.
    """
    G = _build_graph(roads_gdf, status_col)
    if G.number_of_nodes() == 0:
        return []

    components = list(nx.connected_components(G))
    if not components:
        return []

    # Largest component = the "rest of the network"
    largest = max(components, key=len)

    isolated = []
    for comp in components:
        if comp == largest:
            continue
        if len(comp) < 2:   # single orphan node — skip
            continue
        nodes = list(comp)
        xs = [n[0] for n in nodes]
        ys = [n[1] for n in nodes]
        cx, cy = np.mean(xs), np.mean(ys)
        isolated.append({
            "centroid_utm": [round(cx, 0), round(cy, 0)],
            "node_count": len(nodes),
        })

    return isolated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def analyze_network() -> dict:
    roads_path = os.path.join(config.DATA_RAW, config.LAYERS["roads"])

    if not os.path.exists(roads_path):
        print(f"❌  Roads file not found: {roads_path}")
        print("    Run 01_download_osm.py first.")
        return {}

    print("   🛣️   Loading road network …")
    roads_base = _load_roads(roads_path)
    print(f"      {len(roads_base)} road segments loaded.")

    evacuation_summary = {}

    for ts, info in config.SCENARIOS.items():
        depth_path = os.path.join(config.DATA_TIF, info["depth"])

        if not os.path.exists(depth_path):
            print(f"   ⏩  Skipping {ts}: depth raster not found.")
            continue

        print(f"   🌊  Processing {info['label']} …")
        roads = roads_base.copy()

        # --- Sample depth along each road segment ---
        with rasterio.open(depth_path) as d_src:
            # If raster is in geographic CRS, we need to sample in that CRS
            if d_src.crs and d_src.crs != CRS.from_epsg(32629):
                roads_sample = roads.to_crs(d_src.crs.to_epsg() or "EPSG:4326")
            else:
                roads_sample = roads

            depths = []
            for geom in roads_sample.geometry:
                depths.append(_sample_max_depth_along_segment(geom, d_src))

        roads["flood_depth_m"] = depths

        # --- Classify each segment ---
        classifications = roads["flood_depth_m"].apply(_classify_road)
        roads["status"]       = [c["status"]       for c in classifications]
        roads["color"]        = [c["color"]         for c in classifications]
        roads["passable"]     = [c["passable"]      for c in classifications]
        roads["emergency_ok"] = [c["emergency_ok"]  for c in classifications]

        # --- Network isolation analysis ---
        isolated = _find_isolated_communities(roads)

        # --- Counts ---
        n_total      = len(roads)
        n_passable   = int((roads["status"] == "passable").sum())
        n_emergency  = int((roads["status"] == "emergency_only").sum())
        n_impassable = int((roads["status"] == "impassable").sum())

        # --- Output GeoJSON (geographic CRS for Mapbox) ---
        out_gdf  = roads.to_crs(config.GEO_CRS).reset_index(drop=True)
        keep_cols = [c for c in ["geometry", "osmid", "name", "highway",
                                  "flood_depth_m", "status", "color",
                                  "passable", "emergency_ok"]
                     if c in out_gdf.columns]
        out_gdf  = out_gdf[keep_cols]

        out_path = os.path.join(config.DATA_OUT, f"road_passability_{ts}.geojson")
        out_gdf.to_file(out_path, driver="GeoJSON")

        evacuation_summary[ts] = {
            "label":              info["label"],
            "segments_total":     n_total,
            "segments_passable":  n_passable,
            "segments_emergency": n_emergency,
            "segments_impassable":n_impassable,
            "pct_blocked":        round(100 * n_impassable / n_total, 1) if n_total else 0,
            "isolated_communities": len(isolated),
            "isolated_details":   isolated,
        }

        print(f"      ✅  {n_passable} passable | {n_emergency} emergency-only | "
              f"{n_impassable} impassable | {len(isolated)} isolated communities")
        print(f"          Saved → {out_path}")

    # --- Write evacuation summary ---
    evac_path = os.path.join(config.DATA_OUT, "evacuation_summary.json")
    with open(evac_path, "w") as f:
        json.dump(evacuation_summary, f, indent=2)
    print(f"\n   📊  Evacuation summary → {evac_path}")

    return evacuation_summary


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("🛣️   NETWORK ANALYSIS  (Issue #16)")
    print("=" * 55)
    analyze_network()