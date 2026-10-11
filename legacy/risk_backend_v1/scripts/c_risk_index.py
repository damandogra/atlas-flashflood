"""
03_risk_index.py
================
Issue #15 — Composite Risk Index (CRI) raster.

CRI = 0.5 × Physical Hazard  +  0.3 × Population Exposure  +  0.2 × Vulnerability

All three input layers are normalised 0-1 before combining.
Outputs one CRI GeoTIFF per scenario to data/outputs/cri_T*.tif.
Also writes cri_summary.json with zonal statistics.

Usage:
    python 03_risk_index.py
"""

import os
import sys
import json
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.crs import CRS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


# ---------------------------------------------------------------------------
# Normalisation helper
# ---------------------------------------------------------------------------

def _norm(arr: np.ndarray) -> np.ndarray:
    """Min-max normalise to [0, 1], ignoring NaN."""
    mn, mx = np.nanmin(arr), np.nanmax(arr)
    if mx == mn:
        return np.zeros_like(arr)
    return (arr - mn) / (mx - mn)


# ---------------------------------------------------------------------------
# Raster alignment helper
# ---------------------------------------------------------------------------

def _align_to_reference(src_path: str, ref_meta: dict,
                         ref_transform, ref_crs) -> np.ndarray:
    """
    Read a raster and reproject/resample it to match the reference grid.
    Returns a 2-D float32 array.
    """
    with rasterio.open(src_path) as src:
        dest = np.empty(
            (ref_meta["height"], ref_meta["width"]), dtype=np.float32
        )
        reproject(
            source=rasterio.band(src, 1),
            destination=dest,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=ref_transform,
            dst_crs=ref_crs,
            resampling=Resampling.bilinear,
        )
    dest = dest.astype(float)
    dest[dest < 0] = np.nan
    return dest


# ---------------------------------------------------------------------------
# Hazard layer from depth + velocity
# ---------------------------------------------------------------------------

def _build_hazard_layer(depth: np.ndarray, velocity: np.ndarray) -> np.ndarray:
    """
    Physical hazard score using HR Wallingford formula, normalised 0-1.
    HR = depth × (velocity + 0.5) + debris_factor
    Reclassified depth adds a step function component:
        0.3 m → low=0.25,  1.0 m → med=0.5,  2.0 m → high=0.75,  >2.0 → extreme=1.0
    Final hazard = 0.6 × norm(HR) + 0.4 × norm(depth_class)
    """
    hr = depth * (velocity + 0.5) + config.PARAMS["debris_factor"]
    hr_norm = _norm(hr)

    # Depth reclassification
    depth_class = np.zeros_like(depth)
    depth_class[depth >= 0.3] = 0.25
    depth_class[depth >= 1.0] = 0.50
    depth_class[depth >= 2.0] = 0.75
    depth_class[depth >  2.0] = 1.00   # will overwrite previous
    depth_class[depth >  2.0] = 1.00

    hazard = 0.6 * hr_norm + 0.4 * depth_class
    return np.clip(hazard, 0, 1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_risk_index() -> dict:
    pop_path = os.path.join(config.DATA_RAW, config.LAYERS["population"])
    summary  = {}

    for ts, info in config.SCENARIOS.items():
        depth_path = os.path.join(config.DATA_TIF, info["depth"])
        vel_path   = os.path.join(config.DATA_TIF, info["vel"])

        if not os.path.exists(depth_path):
            print(f"   ⏩  Skipping {ts}: depth raster missing.")
            continue

        print(f"   🗺️   Building CRI for {info['label']} …")

        # --- Use depth raster as the reference grid ---
        with rasterio.open(depth_path) as d_src:
            ref_meta      = d_src.meta.copy()
            ref_transform = d_src.transform
            ref_crs       = d_src.crs
            depth_raw     = d_src.read(1).astype(float)
            nodata        = d_src.nodata

        if nodata is not None:
            depth_raw[depth_raw == nodata] = np.nan
        depth_raw[depth_raw < 0] = np.nan

        # --- Velocity layer ---
        if os.path.exists(vel_path):
            velocity_raw = _align_to_reference(vel_path, ref_meta,
                                               ref_transform, ref_crs)
        else:
            print(f"      ⚠️  Velocity raster missing for {ts} — using zeros.")
            velocity_raw = np.zeros_like(depth_raw)

        # --- Hazard layer (H) ---
        H = _build_hazard_layer(depth_raw, velocity_raw)

        # --- Population exposure layer (E) ---
        if os.path.exists(pop_path):
            E_raw = _align_to_reference(pop_path, ref_meta,
                                        ref_transform, ref_crs)
            E = _norm(np.nan_to_num(E_raw, nan=0.0))
        else:
            print("      ⚠️  WorldPop raster missing — using uniform exposure 0.5.")
            E = np.full_like(depth_raw, 0.5)

        # --- Vulnerability layer (V) ---
        # For rural semi-arid Morocco the spatially uniform proxy is 0.3.
        # Future enhancement: read a land-cover raster for cell-level V.
        V = np.full_like(depth_raw, config.PARAMS["vuln_default"])

        # --- CRI = 0.5H + 0.3E + 0.2V ---
        w = config.PARAMS["cri_weights"]
        CRI = w["hazard"] * H + w["exposure"] * E + w["vulnerability"] * V
        CRI = np.clip(CRI, 0, 1)

        # Mask cells where depth is NaN (outside raster extent)
        CRI[np.isnan(depth_raw)] = np.nan

        # --- Write output raster ---
        out_meta = ref_meta.copy()
        out_meta.update(dtype=rasterio.float32, count=1, nodata=-9999)

        out_path = os.path.join(config.DATA_OUT, f"cri_{ts}.tif")
        with rasterio.open(out_path, "w", **out_meta) as dst:
            band = np.where(np.isnan(CRI), -9999, CRI).astype(np.float32)
            dst.write(band, 1)

        # --- Summary stats ---
        valid = CRI[~np.isnan(CRI)]
        summary[ts] = {
            "label":    info["label"],
            "cri_mean": round(float(np.mean(valid)), 3),
            "cri_max":  round(float(np.max(valid)),  3),
            "cri_p90":  round(float(np.percentile(valid, 90)), 3),
            "cells_high_risk": int(np.sum(valid > 0.6)),  # CRI > 0.6 = high
        }

        print(f"      ✅  CRI mean={summary[ts]['cri_mean']:.3f}  "
              f"max={summary[ts]['cri_max']:.3f}  "
              f"high-risk cells={summary[ts]['cells_high_risk']}")
        print(f"          Saved → {out_path}")

    # Write summary
    summary_path = os.path.join(config.DATA_OUT, "cri_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n   📊  CRI summary → {summary_path}")

    return summary


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("📊  COMPOSITE RISK INDEX  (Issue #15)")
    print("=" * 55)
    build_risk_index()