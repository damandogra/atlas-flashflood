# Forecast and replays (Phase 5)

## From weather forecast to flood impacts

The forecast logic exists twice: in `pipeline/forecast/core.py` (Python) and in `web/src/lib/forecast.ts` (the browser). A parity test (`tests/test_forecast.py` writes the fixture, `web/src/lib/forecast.test.ts` checks it) keeps the two identical.

**1. Rain forecast**
- Source: Open-Meteo hourly forecasts for the 15 ERA5-Land cells over the catchment, area-weighted exactly as the design rainfall.
- Deterministic models: ECMWF IFS 0.25°, NOAA GFS and DWD ICON (`rain + showers`).
- Ensemble: ECMWF ENS, 51 members (`precipitation − snowfall`; Open-Meteo snowfall in cm × 10/7 gives mm of water equivalent).
- Correction: the same areal bias correction as the design rainfall (×1.43). Forecast models share ERA5's coarse-grid smoothing of extremes.

**2. Wettest 24 h**
- This is the largest running 24 h total in the next 7 days, plus the hour of peak rain within that window.

**3. Soil moisture**
- Measured as rain in the previous 5 days (Open-Meteo `past_days`), classified as dry, normal or wet using the NEH-4 limits of 12.7 and 27.9 mm (AMC I, II and III).

**4. Equivalent depth**
- This is the AMC II depth that gives the same SCS runoff over the 21 sub-basins as the forecast depth under the actual soil moisture.
- Example: 74 mm on dry soil behaves like 46 mm (Oct 1987 replay).

**5. Library match**
- The largest library storm not above the equivalent depth. The library holds 13 storms, from 20 to 160 mm / 24 h, each with full 2D results and impacts.
- The library's time axis is aligned so its rain burst (t = 12 h) sits on the forecast's peak hour. That gives every impact, deadline and closure a **real clock time**.

**6. Impact-based alert**

| Level | Rule |
|---|---|
| Red | ensemble P(≥ 50-year flood) ≥ 30%, or the ECMWF best guess ≥ 25-year |
| Orange | P(≥ 10-year) ≥ 30%, or best guess ≥ 5-year |
| Yellow | P(≥ 2-year) ≥ 30%, or best guess ≥ the 25 mm library storm (first impacts) |
| Green | otherwise |

**Why match against a library?** NWP hourly rain is as smooth as ERA5's at sub-daily scales (its 1 h / 24 h ratio is about 0.15, against 0.28 from IMERG). So the forecast is used for **how much** rain falls and **when**, while the library's IMERG-shaped storms supply the intensities. Precomputing the 2D floods is what lets a static site deliver flood maps for any forecast in milliseconds.

## Where it runs

- **In the browser:** every page load computes the alert live from Open-Meteo. If that fails, the page falls back to `data/forecast/latest.json`.
- **In GitHub Actions** (`.github/workflows/deploy.yml`):
  - Every 6 hours it runs `python -m pipeline.forecast.live --meta web/public/data/meta.json`. That needs only numpy, pandas and requests.
  - It bakes the result into the site and stores each forecast as a 90-day workflow artifact, so forecasts can be verified later.
  - Nothing is committed back to the repository.

## Replays (exercise mode)

`python -m pipeline.forecast.replay` runs the 8 largest ERA5-Land storms since 1950 through the same logic, with GPM IMERG alongside for comparison.

| Event | 24 h rain (corrected) | Soil | Equivalent | Library flood |
|---|---|---|---|---|
| 22 Nov 2014: southern Morocco floods (first pulse) | 73.9 mm | normal | 73.9 mm | 25-year |
| 26 Oct 1987 | 74.0 mm | dry | 46.2 mm | 5-year |
| 13 Apr 2025 | 72.7 mm | dry | 45.1 mm | 2-year |
| 01 Nov 1971 | 70.8 mm | normal | 70.8 mm | 25-year |
| 19 Sep 2008 | 62.0 mm | normal | 62.0 mm | 10-year |
| 10 Nov 1988 | 54.1 mm | wet | 72.1 mm | 25-year |

IMERG and ERA5 disagree on several of these events (for example 13 Apr 2025: 51 mm raw ERA5 vs 15 mm IMERG). This is real observational uncertainty, and the app shows both values.
