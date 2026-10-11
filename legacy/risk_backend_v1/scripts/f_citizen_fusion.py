"""
06_citizen_fusion.py
====================
Issue #34 — Citizen signal fusion.

Merges community observations with the model CRI raster:

    Fused CRI = (1 - w) × model_CRI  +  w × citizen_signal

where w = config.PARAMS["citizen_weight"] = 0.3 (Poser & Dransch 2010).

citizen_signal per raster cell:
  = normalised(sum of severity scores of observations within RADIUS_M metres)

Outputs:
  data/outputs/cri_fused_T*.tif     — fused raster
  data/outputs/fusion_flags.geojson — cells where citizen signal > model CRI by DELTA_THRESHOLD

Usage:
    python 06_citizen_fusion.py
"""

import os
import sys
import json
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.transform import rowcol
from rasterio.crs import CRS
from shapely.geometry import Point


import config
from scripts import e_citizen as citizen_store

# Radius within which an observation affects a raster cell
RADIUS_M = 500      # 500 m influence radius per observation
DELTA_THRESHOLD = 0.2   # Flag cells where citizen signal exceeds model by this much


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_citizen_layer(observations: list, ref_meta: dict,
                         ref_transform, ref_crs) -> np.ndarray:
    """
    Rasterise citizen severity scores onto the CRI grid.

    For each observation, add its severity score (1/2/3) to every pixel
    within RADIUS_M. Then normalise the entire layer 0-1.

    Returns a 2-D float array the same shape as the CRI raster.
    """
    height = ref_meta["height"]
    width  = ref_meta["width"]
    signal = np.zeros((height, width), dtype=float)

    if not observations:
        return signal

    # Determine pixel size in metres for radius conversion
    # ref_crs may be geographic (degrees) — compute approximate metres per pixel
    crs = CRS.from_user_input(ref_crs) if not isinstance(ref_crs, CRS) else ref_crs
    if crs.is_geographic:
        # 1 degree latitude ≈ 111 000 m; use that for pixel size
        px_size_m = abs(ref_transform.e) * 111_000
    else:
        px_size_m = abs(ref_transform.e)   # metres per pixel (UTM)

    radius_px = max(1, int(RADIUS_M / px_size_m))

    for obs in observations:
        # Transform lon/lat to row/col in the raster
        lon, lat = obs["lon"], obs["lat"]

        # If raster is in projected CRS, convert lon/lat to that CRS first
        if not crs.is_geographic:
            import pyproj
            transformer = pyproj.Transformer.from_crs(
                "EPSG:4326", crs.to_epsg() or "EPSG:4326", always_xy=True
            )
            x, y = transformer.transform(lon, lat)
        else:
            x, y = lon, lat

        try:
            row_c, col_c = rowcol(ref_transform, x, y)
        except Exception:
            continue

        # Add severity to pixels within radius
        r0 = max(0, row_c - radius_px)
        r1 = min(height, row_c + radius_px + 1)
        c0 = max(0, col_c - radius_px)
        c1 = min(width,  col_c + radius_px + 1)

        for r in range(r0, r1):
            for c in range(c0, c1):
                dist_px = np.hypot(r - row_c, c - col_c)
                if dist_px <= radius_px:
                    # Weight by inverse distance (bell-shaped kernel)
                    w = 1.0 - (dist_px / (radius_px + 1))
                    signal[r, c] += obs["severity"] * w

    # Normalise 0-1
    if signal.max() > 0:
        signal /= signal.max()

    return signal


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fuse() -> dict:
    """
    Run fusion for all available scenario CRI rasters.
    Returns a dict of per-scenario stats.
    """
    # Load citizen observations
    citizen_store.init_db()
    observations = citizen_store.get_observations()
    print(f"   📡  {len(observations)} citizen observations loaded.")

    w_citizen = config.PARAMS["citizen_weight"]
    w_model   = 1.0 - w_citizen
    summary   = {}
    flags_all = []

    for ts, info in config.SCENARIOS.items():
        cri_path = os.path.join(config.DATA_OUT, f"cri_{ts}.tif")
        if not os.path.exists(cri_path):
            print(f"   ⏩  Skipping {ts}: CRI raster not found. "
                  f"Run 03_risk_index.py first.")
            continue

        print(f"   🔀  Fusing {info['label']} …")

        with rasterio.open(cri_path) as src:
            model_cri = src.read(1).astype(float)
            nodata    = src.nodata
            ref_meta  = src.meta.copy()
            ref_transform = src.transform
            ref_crs   = src.crs

        if nodata is not None:
            model_cri[model_cri == nodata] = np.nan

        # Build citizen signal raster
        citizen_layer = _build_citizen_layer(
            observations, ref_meta, ref_transform, ref_crs
        )

        # Fused CRI
        fused = w_model * np.nan_to_num(model_cri, nan=0.0) + w_citizen * citizen_layer
        fused = np.clip(fused, 0, 1)
        fused[np.isnan(model_cri)] = np.nan

        # Write fused raster
        out_meta = ref_meta.copy()
        out_meta.update(dtype=rasterio.float32, nodata=-9999)
        out_path = os.path.join(config.DATA_OUT, f"cri_fused_{ts}.tif")
        with rasterio.open(out_path, "w", **out_meta) as dst:
            band = np.where(np.isnan(fused), -9999, fused).astype(np.float32)
            dst.write(band, 1)

        # Identify flag cells: citizen signal significantly exceeds model CRI
        delta = citizen_layer - np.nan_to_num(model_cri, nan=0.0)
        flag_mask = (delta > DELTA_THRESHOLD) & ~np.isnan(model_cri)
        flag_count = int(flag_mask.sum())

        # Convert flagged pixels to point GeoJSON features
        if flag_count > 0:
            rows_f, cols_f = np.where(flag_mask)
            xs, ys = rasterio.transform.xy(ref_transform, rows_f, cols_f)
            for x, y, r, c in zip(xs, ys, rows_f, cols_f):
                flags_all.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [x, y]},
                    "properties": {
                        "scenario":       ts,
                        "model_cri":      round(float(model_cri[r, c]), 3),
                        "citizen_signal": round(float(citizen_layer[r, c]), 3),
                        "delta":          round(float(delta[r, c]), 3),
                    },
                })

        valid = fused[~np.isnan(fused)]
        summary[ts] = {
            "label":              info["label"],
            "fused_cri_mean":     round(float(np.mean(valid)), 3),
            "fused_cri_max":      round(float(np.max(valid)),  3),
            "flag_cells":         flag_count,
            "citizen_obs_used":   len(observations),
        }

        print(f"      ✅  Fused CRI mean={summary[ts]['fused_cri_mean']:.3f}  "
              f"flags={flag_count}")
        print(f"          Saved → {out_path}")

    # Write fusion flags GeoJSON
    flags_geojson = {"type": "FeatureCollection", "features": flags_all}
    flags_path = os.path.join(config.DATA_OUT, "fusion_flags.geojson")
    with open(flags_path, "w") as f:
        json.dump(flags_geojson, f)
    print(f"\n   🚩  Fusion flags → {flags_path}  ({len(flags_all)} flagged cells)")

    return summary


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("🔀  CITIZEN FUSION  (Issue #34)")
    print("=" * 55)
    fuse()