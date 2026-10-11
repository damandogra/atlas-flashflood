"""Land surface parameters: hydrologic soil group, SCS Curve Number and Manning's n grids.

Usage: python -m pipeline.data.landsurface      (after pipeline.data.terrain)

Outputs (data/interim/): hsg.tif, cn_amc2.tif, manning.tif; adds CN / land-cover shares to basin_model.json
"""

import json

import numpy as np

from pipeline import config, grid

INTERIM = config.INTERIM

# OpenLandMap USDA texture class -> hydrologic soil group (1=A .. 4=D), after USDA NEH 630 ch. 7
#  1 Cl, 2 SiCl, 3 SaCl, 4 ClLo, 5 SiClLo, 6 SaClLo, 7 Lo, 8 SiLo, 9 SaLo, 10 Si, 11 LoSa, 12 Sa
TEXTURE_HSG = {1: 4, 2: 4, 3: 4, 4: 4, 5: 4, 6: 3, 7: 2, 8: 2, 9: 1, 10: 2, 11: 1, 12: 1}

# Steep bare ground in the High Atlas is mostly rock outcrop / shallow regolith: treat as group D
# (HYSOGs250m assigns D where depth to bedrock < 50 cm; we have no depth-to-bedrock layer at 30 m).
ROCK_SLOPE_DEG = 20

# ESA WorldCover class -> CN for HSG A, B, C, D (AMC II). USDA TR-55 tables 2-2a..2-2d,
# arid/semi-arid rangeland rows in poor condition where they exist.
CN_TABLE = {
    10: (36, 60, 73, 79),    # tree cover            - woods, fair
    20: (63, 77, 85, 88),    # shrubland             - desert shrub, poor
    30: (68, 80, 87, 93),    # grassland             - herbaceous (grass/weeds/low brush), poor
    40: (63, 75, 83, 87),    # cropland              - small grain, straight row, good (irrigated terraces)
    50: (77, 85, 90, 92),    # built-up              - residential, 65% impervious
    60: (77, 86, 91, 94),    # bare / sparse         - fallow, bare soil
    70: (77, 86, 91, 94),    # snow and ice          - treated as bare
    80: (98, 98, 98, 98),    # permanent water
    90: (78, 78, 78, 78),    # herbaceous wetland
    100: (77, 86, 91, 94),   # moss and lichen       - treated as bare
}

# Manning's n for overland / floodplain flow (Chow 1959; HEC-RAS 2D land-cover guidance)
MANNING = {10: 0.10, 20: 0.06, 30: 0.035, 40: 0.04, 50: 0.08, 60: 0.03,
           70: 0.03, 80: 0.03, 90: 0.07, 100: 0.03}
CHANNEL_N = 0.045          # gravel-cobble mountain wadi bed
CHANNEL_KM2 = 5.0          # drainage area above which a cell is treated as channel


def run():
    catch = grid.read(INTERIM / "catchment.tif").astype(bool)
    wc = grid.read(config.RAW / "worldcover.tif")
    tex = grid.read(config.RAW / "soil_texture_b0.tif")
    dem = grid.read(INTERIM / "dem_cond.tif")
    acc = grid.read(INTERIM / "acc_km2.tif")
    slope = np.degrees(np.arctan(np.hypot(*np.gradient(dem, config.GRID_RES_M))))

    hsg = np.vectorize(lambda t: TEXTURE_HSG.get(int(t), 2), otypes=["uint8"])(tex)   # default B
    hsg[(wc == 60) & (slope > ROCK_SLOPE_DEG)] = 4

    wc_safe = np.where(np.isin(wc, list(CN_TABLE)), wc, 60)    # nodata/unknown -> bare
    lut = np.zeros((256, 5), dtype="float32")
    for cls, cns in CN_TABLE.items():
        lut[cls, 1:] = cns
    cn = lut[wc_safe, hsg].astype("float32")

    n = np.vectorize(lambda c: MANNING.get(int(c), 0.035), otypes=["float32"])(wc_safe)
    n[acc >= CHANNEL_KM2] = CHANNEL_N

    grid.write(INTERIM / "hsg.tif", hsg, "uint8", 0)
    grid.write(INTERIM / "cn_amc2.tif", np.where(catch, cn, 0).astype("float32"), "float32", 0)
    grid.write(INTERIM / "manning.tif", n, "float32")

    # --- per sub-basin attributes ---------------------------------------------------
    labels = grid.read(INTERIM / "subbasins.tif")
    model_path = INTERIM / "basin_model.json"
    model = json.loads(model_path.read_text(encoding="utf8"))
    for sb in model["subbasins"]:
        m = labels == sb["id"]
        # Area-weighting retention S (not CN) preserves the runoff of the mixed sub-basin better
        s_mean = np.mean(25400.0 / cn[m] - 254.0)
        sb["cn_amc2"] = round(float(25400.0 / (s_mean + 254.0)), 1)
        sb["cn_amc2_area_mean"] = round(float(cn[m].mean()), 1)
        sb["landcover_pct"] = {str(int(k)): round(100.0 * v / m.sum(), 1)
                               for k, v in zip(*np.unique(wc_safe[m], return_counts=True))}
        sb["impervious_pct"] = round(float(100.0 * (wc_safe[m] == 50).mean() * 0.65), 2)
    model["cn_source"] = "ESA WorldCover v200 + OpenLandMap USDA texture -> HSG; TR-55 CN; bare >20 deg slope = HSG D"
    model_path.write_text(json.dumps(model, indent=1, ensure_ascii=False), encoding="utf8")

    print(f"  CN (AMC II) catchment mean {cn[catch].mean():.1f}, range {cn[catch].min():.0f}-{cn[catch].max():.0f}")
    print(f"  HSG shares: " + ", ".join(f"{'ABCD'[k - 1]} {100 * (hsg[catch] == k).mean():.0f}%" for k in (1, 2, 3, 4)))
    print(f"  Manning n: channel cells {(acc[catch] >= CHANNEL_KM2).sum()}, overland mean {n[catch].mean():.3f}")


if __name__ == "__main__":
    run()
