"""Single source of truth for the Atlas v2 pipeline: paths, CRS and study area."""

from pathlib import Path

# --- Paths -------------------------------------------------------------------
REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"                  # gitignored working data
RAW = DATA / "raw"                    # downloads (DEM, land cover, soils, rainfall, OSM, WorldPop)
INTERIM = DATA / "interim"            # conditioned DEM, flow grids, CN / Manning grids
RUNS = DATA / "runs"                  # hydrology + 2D model outputs per scenario
WEB_DATA = REPO / "web" / "public" / "data"   # committed bundle served by GitHub Pages
HEC = REPO / "hec"                    # HEC-HMS / HEC-RAS exports for cross-validation

for _d in (RAW, INTERIM, RUNS):
    _d.mkdir(parents=True, exist_ok=True)

# --- Coordinate systems -------------------------------------------------------
CRS_WORK = "EPSG:32629"   # UTM 29N, metres - all modelling happens here
CRS_WEB = "EPSG:4326"     # WGS84 - GeoJSON / map output

# --- Study area ---------------------------------------------------------------
# Download extent: generous box around the Ounila valley (Telouet -> Tighza -> Ait Ben Haddou)
# so that the true catchment, delineated from the DEM in Phase 1, fits inside it.
# (min_lon, min_lat, max_lon, max_lat)
AOI_BBOX = (-7.50, 30.95, -6.80, 31.60)

# Hackathon v1 hand-drawn study polygon, kept only as a reference for the area of interest.
V1_STUDY_POLYGON = [
    (-7.152786, 31.281004), (-7.173386, 31.285698), (-7.185402, 31.28159),
    (-7.188835, 31.293033), (-7.171326, 31.29626), (-7.181625, 31.307407),
    (-7.172356, 31.31386), (-7.179909, 31.337616), (-7.175789, 31.351397),
    (-7.179222, 31.361658), (-7.165833, 31.368694), (-7.159996, 31.366935),
    (-7.14592, 31.370746), (-7.135277, 31.367228), (-7.118111, 31.37397),
    (-7.102661, 31.378074), (-7.061119, 31.370453), (-7.053223, 31.361951),
    (-7.039146, 31.363417), (-7.025414, 31.338202), (-7.002754, 31.336736),
    (-6.969452, 31.340255), (-6.971855, 31.328232), (-6.979065, 31.325006),
    (-6.990395, 31.313274), (-7.023354, 31.279537), (-7.03743, 31.278656),
    (-7.049446, 31.284525), (-7.059746, 31.277483), (-7.074509, 31.280417),
    (-7.082062, 31.268093), (-7.106094, 31.274842), (-7.108841, 31.28071),
    (-7.124977, 31.283644), (-7.14077, 31.280417), (-7.152786, 31.281004),
]

GRID_RES_M = 30           # model grid resolution (Copernicus GLO-30)

# --- Earth Engine ---------------------------------------------------------------
EE_PROJECT = "ee-damandograa"
