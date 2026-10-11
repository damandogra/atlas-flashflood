# Atlas: flash-flood decision support for the Ounila valley (High Atlas, Morocco)

**Live site:** https://damandogra.github.io/atlas-flashflood/

Atlas answers one question for the people who have to act when a storm comes:

> **Rain is coming. What will happen, where, when, and what should we do first?**

It is a static web app (GitHub Pages) on top of a physically based model chain. Every stage is grounded in observed data and checked against measurements.

| Mode | What it gives a planner |
|---|---|
| **Situation** | A live 7-day forecast (ECMWF, GFS, ICON + a 51-member ensemble) turned into an **impact-based alert**: the probability of reaching each flood level, and when |
| **Impact** | Village-by-village effects: buildings and residents reached by water (by hazard class), houses at risk of collapse, the time water arrives, and when each village is **cut off by road** |
| **Act** | An early-action plan with owners and clock-time deadlines, generated from an editable playbook, plus **evacuation routes** that avoid roads unsafe at that moment |
| **Plan** | Mitigation tested with the models: road links to flood-proof, headwater restoration, check dams |
| **Reports** | Community field reports (Supabase), shown on the map |
| **Export / Method** | A printable situation report, data downloads, methods, validation and limitations |

A timeline animates the flood wave hour by hour. Past storms (for example the **November 2014 floods**) can be replayed through the same logic, for exercises and training.

## The model chain

| Stage | Method | Data | Grounding |
|---|---|---|---|
| Terrain | Catchment delineated from the DEM: 730.9 km², 21 sub-basins at villages and confluences | Copernicus GLO-30 | Matches the DRPE **Agouillal** gauge (740 km²) |
| Rainfall | GEV (L-moments) of 76 years of hourly *liquid* rain; storm shape from satellite; areal bias correction ×1.43 | ERA5-Land, GPM IMERG V07, GHCN Ouarzazate | Gauge bias and point-to-area factor, bootstrap CIs |
| Hydrology | HEC-HMS methods: SCS-CN, Clark unit hydrograph, Muskingum-Cunge | WorldCover, OpenLandMap soils | **Water balance at Agouillal** (storm runoff 28 mm/yr vs 19–36 observed); peaks within the High Atlas regional envelope (Ourika, Rheraya) |
| Hydraulics | 2D local-inertia solver (LISFLOOD-FP formulation), 30 m, 101 km² of valley corridors; 13 storms from 20 to 160 mm / 24 h | Raw GLO-30 with breached channels | Analytical normal-depth test (±5%), exact mass balance |
| Impacts | DEFRA FD2320 hazard, ARR 2019 vehicle limits, road-graph isolation every 30 min, shelters | 16,653 Google building footprints, OSM roads, fords and facilities, GHS-POP/WorldPop | 15,571 residents (two population products agree within 5%) |
| Forecast | Bias-corrected catchment rain → soil-moisture-equivalent depth → library match → alert | Open-Meteo | Identical results in Python and the browser (parity test) |

The details, the numbers and every source are in [`docs/`](docs/):
- [`data.md`](docs/data.md)
- [`hydrology.md`](docs/hydrology.md)
- [`hydraulics.md`](docs/hydraulics.md)
- [`impact.md`](docs/impact.md)
- [`forecast.md`](docs/forecast.md)

## Repository

```
pipeline/            Python model chain (run in order, see RUN.md)
  data/              downloads, terrain, land surface, rainfall
  hydrology/         HEC-HMS-equivalent engine, design floods, HEC-HMS export
  hydraulics/        2D solver, scenario library, HEC-RAS export
  impact/            exposure prep, impact engine, playbook.yaml, actions, mitigation
  forecast/          shared core, live forecast, historical replays
  export/web.py      builds the static data bundle for the web app
web/                 React + MapLibre app (Vite); web/public/data is the published bundle
hec/                 HEC-HMS project and HEC-RAS 2D package for independent cross-checks
docs/                methods, validation, figures, Supabase schema
tests/               Python tests (rainfall, HMS, 2D solver, forecast); web/ has the TS parity test
legacy/              the original 48-hour hackathon code (reference only)
.github/workflows/   deploy.yml - builds, refreshes the forecast every 6 h, publishes to Pages
```

## Run it

- **Web app, locally.** It needs Node 20 or later.
  ```bash
  cd web && npm ci && npm run dev
  ```
  Then open http://localhost:5173/atlas-flashflood/.
- **Rebuilding the model** from scratch (Earth Engine access is needed): see [`RUN.md`](RUN.md).
- **Updating the live site after a model change:** the site reads the committed bundle in `web/public/data/`, and CI only refreshes the forecast. Run `python -m pipeline.export.web`, then commit and push the bundle (details in [`RUN.md`](RUN.md#updating-the-live-site-after-a-model-change)).
- **Deploying:**
  1. Push to `main`.
  2. Under Settings → Pages, set the source to **GitHub Actions**.
  3. Optionally add the repository variables `SUPABASE_URL` and `SUPABASE_ANON_KEY` for shared field reports (schema in [`docs/supabase.sql`](docs/supabase.sql)).

## Limitations

Atlas is a research prototype for planning and training. It is **not a certified operational warning service**.
- The 30 m terrain smooths narrow gorges.
- No flood-peak record is public for this river, so peaks are bounded by regional evidence and the outlet water balance, not calibrated event by event.
- Forecasts inherit numerical weather prediction (NWP) errors in convective rain.
- Residents per building are estimates.

Built at the Cassini Hackathon (Atlas v1), then rebuilt as Atlas v2.
