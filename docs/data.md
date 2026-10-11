# Data foundation (Phase 1)

All layers sit on one grid: **30 m, UTM 29N (EPSG:32629)**, 2262 × 2440 cells, defined in
`pipeline/grid.py` from `config.AOI_BBOX`.

## Reproduce

```bash
conda activate atlas
python -m pipeline.data.download dem landcover soil places   # Earth Engine + Overpass
python -m pipeline.data.terrain                              # catchment, sub-basins, streams, HAND
python -m pipeline.data.download rain imerg                  # need the catchment (Earth Engine)
python -m pipeline.data.landsurface                          # HSG, Curve Number, Manning's n
python -m pipeline.data.rainfall                             # bias, IDF, design storms, events
python -m pipeline.data.figures                              # docs/figures/phase1_*.png
```

Ouarzazate GHCN-Daily is fetched once by hand:
`https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_station/MO000060265.csv.gz` → `data/raw/ghcn_MO000060265.csv.gz`.

## Datasets

| Layer | Source | Resolution | Licence | Used for |
|---|---|---|---|---|
| Elevation | Copernicus DEM GLO-30 (`COPERNICUS/DEM/GLO30`, Earth Engine) | 30 m | Copernicus DEM licence (free, attribution) | Terrain, flow routing, 2D model |
| Land cover | ESA WorldCover v200, 2021 (`ESA/WorldCover/v200`) | 10 m → 30 m (mode) | CC BY 4.0 | Curve Number, Manning's n |
| Soil texture | OpenLandMap USDA texture class (`OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02`) | 250 m | CC BY-SA 4.0 | Hydrologic soil group |
| Rainfall (magnitude) | ERA5-Land hourly (`ECMWF/ERA5_LAND/HOURLY`), total precipitation and snowfall, 1950–2025, 20 cells | ~0.1° (≈106 km²), 1 h | Copernicus licence (free, attribution) | 24 h / 48 h extremes, event catalogue |
| Rainfall (storm shape) | GPM IMERG V07 Final (`NASA/GPM_L3/IMERG_V07`), 1998–2025, same 20 cells | 0.1°, 30 min | NASA open data | Sub-daily storm structure, event cross-check |
| Rain gauge | GHCN-Daily Ouarzazate `MO000060265` (NOAA NCEI) | daily | Public domain | Bias of gridded products |
| Places | OpenStreetMap `place=*` via Overpass | points | ODbL | Control points / village names |
| Buildings, roads, POIs, population | OSM via osmnx, WorldPop 2020 (reused from v1) | – | ODbL, CC BY 4.0 | Exposure (Phase 4) |

## Catchment and sub-basins

- **Outlet:** Aït Ben Haddou. **Area: 730.9 km²**, elevation 1264–3601 m.
  - The hackathon's hand-drawn polygon covered only part of this.
- **Method:** pysheds. Pits filled, depressions filled, flats resolved, then D8 flow direction and accumulation.
- **Streams:** mapped where the drainage area is at least 1 km² (449 segments).
- **21 sub-basins**, split at:
  - every named OSM village within 500 m of a channel draining at least 5 km². Each village is snapped to the *largest* channel within 500 m, because the main wadi is the dominant hazard.
  - confluences where both branches drain more than 25 km².
- **Merging:** confluence increments under 3 km² are merged into the next sub-basin downstream. Villages are kept unless they own less than 0.5 km².
- **Two main branches meet at Tamdaght:**
  - the western Ounila (Télouet → Ankhsa → Tazlaft), 393 km².
  - the eastern branch (Tighza → Anmiter → Assaka → Taifest), 304 km².
- **Per sub-basin attributes**, in `data/interim/basin_model.json`:
  - area, longest flow path (true D8 lengths), relief, slope and Curve Number.
  - the downstream reach, with its length and slope.

## Curve Number

- **Soil group:** comes from the USDA texture class. The catchment is 87% loam, which maps to group B.
- **Rock adjustment:** bare ground steeper than 20° is set to **group D**, treated as rock outcrop or shallow regolith. This follows the HYSOGs250m rule (depth to bedrock < 50 cm → D), because there is no 30 m bedrock-depth layer.
- **CN values:** USDA TR-55 tables, using the arid/semi-arid rangeland rows in poor condition.
- **Catchment mean CN is 84.** Sub-basins range from 77–82 in the grassy headwaters to 85–88 on the bare lower slopes.
- **Sub-basin CN:** computed by averaging retention S, not CN, over the area. This keeps the sub-basin's runoff consistent with that of its mixed cells.

## Rainfall

Each piece of the design rainfall comes from the data source best suited to it.

**1. Liquid precipitation only.**
- ERA5-Land snowfall is subtracted from total precipitation. Snow makes up 21% of the catchment's precipitation; it melts over days and does not drive flash floods.
- Mean annual liquid areal rainfall is 337 mm.

**2. Magnitude: ERA5-Land, 76 years.**
- Annual maxima of 24 h and 48 h totals, fitted with a GEV distribution using L-moments (Hosking 1990), with 500 bootstrap resamples.
- Fitted at catchment scale (area-weighted) and at cell scale (median across the 15 cells over the catchment).

**3. Correction = point bias × point-to-cell areal reduction.**
- **Point bias: 1.68** (90% CI 1.16–2.25). This is Ouarzazate gauge / ERA5 at the gauge, mean annual-maximum day, from 20 complete gauge years.
  - IMERG at the gauge agrees with ERA5 (18.4 vs 18.0 mm), against 44.3 mm at the gauge, in the 5 years where all three overlap.
  - So *both* gridded products sit below the gauge. Part of that gap is real product bias, and part is the natural difference between a point and a ~106 km² average.
- **Point-to-cell areal reduction factor (ARF): 0.85** (range 0.75–0.95). **Assumed**, from the literature.
- **Applied correction:** central **×1.43**, low ×0.87, high ×2.14.
- In the mountains, IMERG and ERA5 agree on the mean annual-max 24 h depth (29.8 vs 30.5 mm, 1998–2025).

**4. Storm shape: IMERG, measured.**
- The ratio of mean annual-max D-hour depth to 24 h depth, median over the 15 catchment cells, with bootstrap CIs. These ratios are applied directly to the 24 h depth.

| Ratio to the 24 h depth | 1 h | 2 h | 3 h | 6 h | 12 h |
|---|---|---|---|---|---|
| IMERG (used) | 0.28 | 0.42 | 0.53 | 0.69 | 0.85 |
| IMERG 90% CI | 0.26–0.31 | 0.38–0.46 | 0.48–0.58 | 0.64–0.75 | 0.82–0.90 |
| ERA5-Land (not used) | 0.15 | 0.25 | 0.33 | 0.52 | 0.75 |

- ERA5 is too flat at sub-daily scales because it smears convective bursts over ~11 km and whole hours. It is used only for the 24–48 h magnitudes.
- A least-squares Montana exponent through the 24 h point is b = 0.645, reported only as a summary; the measured ratios aren't a pure power law.

**5. Design storms.**
- 24 h alternating-block hyetographs at 15-minute steps.
- Below 1 hour, Bell (1969) ratios are used.
- Generated for every return period, at both scales, at all three levels (low / central / high). The HMS engine interpolates between cell scale and catchment scale by sub-basin area.

| Catchment-average liquid depth, central (mm) | T2 | T10 | T50 | T100 | T500 |
|---|---|---|---|---|---|
| 1 h | 9 | 15 | 21 | 24 | 30 |
| 6 h | 22 | 38 | 52 | 58 | 73 |
| 24 h | 32 | 55 | 75 | 84 | 106 |

**T100 24 h across the three levels: 52 / 84 / 126 mm.** Phase 2 narrows this band by checking simulated peak discharges against regional flood envelope curves and the November 2014 event.

**6. Event catalogue.**
- `rainfall/events.json` lists the 25 largest ERA5 liquid areal 24 h totals, each with the independent IMERG estimate.
- The two products disagree on some events. For example, on 13 Apr 2025 ERA5 gives 51 mm raw and IMERG 15 mm; that is real product uncertainty.
- **November 2014:**
  - 21–23 Nov: 97 mm of liquid rain over 3 days (uncorrected areal).
  - 28–29 Nov: largely snow over the High Atlas, according to ERA5.
  - **20–24 Nov 2014 is the replay and validation event.**

## Assumptions to revisit

1. **Point-to-cell ARF (0.85).** This is now the most influential uncertain parameter. Phase 2 constrains it with discharge checks.
   - Official IDF curves from the Agence du Bassin Hydraulique Souss-Massa-Drâa would let it be tested directly.
2. **The point bias comes from one valley gauge** (1139 m), with only 20 complete years. Its two biggest years, 1995 and 2004, dominate.
3. **Ratios of means:** the IMERG duration ratios are assumed to be the same across return periods (an index-flood-type assumption).
4. **Snowmelt is ignored.** That's appropriate for flash floods, not for spring baseflow.
5. **No depth-to-bedrock layer.** The "steep and bare means group D" rule is a stand-in for one.
6. **WorldCover maps 0% built-up area** (the earthen ksour are not detected), so buildings come from OSM in Phase 4.

## Outputs

These are in `data/interim/`, which is gitignored and regenerated by the commands above:

- **Rasters:** `dem_cond.tif`, `fdir.tif`, `acc_km2.tif`, `hand.tif`, `catchment.tif`, `subbasins.tif`, `hsg.tif`, `cn_amc2.tif`, `manning.tif`.
- **Vectors (WGS84):** `catchment.geojson`, `subbasins.geojson`, `streams.geojson`, `control_points.geojson`.
- **Model inputs:** `basin_model.json`.
- **Rainfall:** `rainfall/idf.json`, `design_storms.json`, `events.json`, `annual_maxima.csv`.
