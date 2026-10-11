# MountainMapping

Hydrological risk assessment and flood modeling for mountainous watersheds using satellite data from Copernicus Sentinel-2 and ERA5-Land.

## Problem Statement

Mountainous regions face critical flood and erosion risks, yet hydrological modeling in these areas is often limited by scarce ground data. This project automates the extraction of satellite-derived inputs (vegetation indices, digital elevation models, historical rainfall) and runs physically based hydrology models to assess flood hazards at the pixel level.

The study area is the **Tighza region in the Atlas Mountains, Morocco**.

## What it does

1. **Satellite data acquisition** — Fetches NDVI (Sentinel-2) and Digital Elevation Model (Copernicus DEM) via the Sentinel Hub API.
2. **Precipitation retrieval** — Queries current and historical rainfall from Open-Meteo (ERA5-Land reanalysis, 1940–present).
3. **Return period analysis** — Fits Gumbel and GEV (Generalized Extreme Value) distributions to annual maxima to estimate extreme rainfall for T10, T50, T100, and T500 events.
4. **Hydrological modeling**:
   - **Curve Number (CN)** — Converts NDVI into runoff potential.
   - **HEC-HMS (SCS method)** — Computes direct runoff from precipitation.
   - **RUSLE** — Estimates soil erosion risk from rainfall, slope, and vegetation.
   - **HEC-RAS 2D (simplified)** — Simulates flow velocity and direction using Manning's equation and elevation gradients.
5. **Scenario generation** — Produces depth, velocity, and flow direction maps for each return period.
6. **Export** — Outputs georeferenced GeoTIFFs (GIS-ready) and PNG visualizations.

## Project structure

```
MountainMapping/
├── src/
│   ├── main.py                         # TBD
│   └── scripts/
│       ├── coordinates.py              # Study area bounding box (Tighza, Morocco)
│       ├── evalscripts.py              # Sentinel Hub evalscripts (NDVI computation)
│       ├── engine.py                   # HydrologyEngine (HEC-HMS, RUSLE, HEC-RAS 2D)
│       ├── get_precipitation.py        # Open-Meteo API client (current + ERA5 historical)
│       ├── gevandgumble.py             # GEV/Gumbel distribution fitting for return periods
│       ├── hec_inputs.py               # Entry point (orchestrates the pipeline)
│       └── export.py                   # GeoTIFF and PNG export utilities
├── tests/                              # Test suite (TBD)
├── docs/                               # Documentation (TBD)
├── Dockerfile                          # (future use) Multi-stage Docker build
├── docker-compose.yml                  # (future use) Postgres + FastAPI services
└── requirements.txt                    # Python dependencies
```

## How to run it

### Prerequisites

- Python 3.14+
- A [Sentinel Hub](https://www.sentinel-hub.com/) account with Client ID and Client Secret

### Setup

```bash
# Clone the repository
git clone <repo-url>
cd MountainMapping

# Create a virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure Sentinel Hub credentials
# Create src/scripts/.env with:
#   SH_CLIENT_ID=your_client_id
#   SH_CLIENT_SECRET=your_client_secret
```

### Run the pipeline

```bash
python src/scripts/hec_inputs.py
```

This will:

1. Authenticate with Sentinel Hub.
2. Download NDVI and DEM tiles for the Tighza bounding box.
3. Fetch historical ERA5 precipitation data.
4. Compute Curve Number, runoff, and erosion risk.
5. Generate depth, velocity, and flow direction GeoTIFFs for T10, T50, T100, and T500 scenarios.

### Docker (not yet implemented)

Docker and docker-compose files are included as a reference for future deployment. They are not currently wired up — the pipeline runs as a standalone Python script.

## Dependencies

- **Geospatial:** rasterio, numpy, geopandas, shapely
- **Satellite:** sentinelhub
- **API:** fastapi, uvicorn, pydantic, requests
- **Environment:** python-dotenv

## License

MIT
