# Rebuilding the Atlas model chain

The whole chain can be regenerated from public data. Everything below writes to `data/`, which is gitignored, except the final web export.

## Setup

```bash
conda env create -f environment.yml && conda activate atlas
earthengine authenticate          # once; uses the Earth Engine project in pipeline/config.py
```

One manual download: the GHCN-Daily file for Ouarzazate, saved to `data/raw/ghcn_MO000060265.csv.gz`.

```bash
curl -o data/raw/ghcn_MO000060265.csv.gz https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_station/MO000060265.csv.gz
```

## Chain (approximate run times)

```bash
# Phase 1 - data
python -m pipeline.data.download dem landcover soil places   # ~3 min
python -m pipeline.data.terrain                              # catchment, sub-basins (~30 s)
python -m pipeline.data.download rain imerg                  # ERA5-Land + IMERG via Earth Engine (~8 min)
python -m pipeline.data.landsurface                          # CN, Manning n
python -m pipeline.data.rainfall                             # bias, storm shape, IDF, design storms (~2 min)
python -m pipeline.data.exposure_data                        # buildings, OSM, WorldPop, population totals

# Phase 2 - hydrology
python -m pipeline.hydrology.scenarios                       # design floods + water-balance/regional checks
python -m pipeline.hydrology.hec_export                      # HEC-HMS project in hec/hms/

# Phase 3 - 2D hydraulics
python -m pipeline.hydraulics.scenarios                      # 13-storm library (~35 min)
python -m pipeline.hydraulics.hec_ras_export                 # HEC-RAS package in hec/ras/

# Phase 4 - impacts
python -m pipeline.impact.prep
python -m pipeline.impact.engine
python -m pipeline.impact.actions                            # from pipeline/impact/playbook.yaml
python -m pipeline.impact.mitigation

# Phase 5 - forecast and replays
python -m pipeline.forecast.replay
python -m pipeline.forecast.live

# Publish the bundle and figures
python -m pipeline.export.web                                # -> web/public/data
python -m pipeline.data.figures && python -m pipeline.hydrology.figures && python -m pipeline.hydraulics.figures

# Tests
python -m pytest tests && (cd web && npx vitest run)
```

## Changing the early-action protocol

Edit `pipeline/impact/playbook.yaml` (owners, lead times, priorities), then run:

```bash
python -m pipeline.impact.actions && python -m pipeline.export.web
```
