import os

# --- 1. DYNAMIC PATH MANAGEMENT ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DIRS = {
    "tif":     os.path.join(BASE_DIR, "data"),           # Person A's TIFs live here
    "raw":     os.path.join(BASE_DIR, "data", "raw"),    # OSM / WorldPop downloads
    "outputs": os.path.join(BASE_DIR, "data", "outputs"),
    "db":      os.path.join(BASE_DIR, "data", "db"),     # SQLite for citizen reports
}

for path in DIRS.values():
    os.makedirs(path, exist_ok=True)

# Shortcuts
DATA_TIF = DIRS["tif"]       # depth_T*.tif  /  velocity_T*.tif  live here
DATA_RAW = DIRS["raw"]
DATA_OUT = DIRS["outputs"]
DATA_DB  = DIRS["db"]

# --- 2. GEOSPATIAL SETTINGS ---
PROJ_CRS = "EPSG:32629"   # UTM 29N  (metre-based calculations)
GEO_CRS  = "EPSG:4326"   # WGS84    (GeoJSON / Mapbox output)

# --- 3. STUDY AREA ---
BUFFER_M = 25000   # 25 km flood influence zone around catchment
CATCHMENT_COORDS = [
    [-7.152786, 31.281004], [-7.173386, 31.285698], [-7.185402, 31.28159],
    [-7.188835, 31.293033], [-7.171326, 31.29626],  [-7.181625, 31.307407],
    [-7.172356, 31.31386],  [-7.179909, 31.337616], [-7.175789, 31.351397],
    [-7.179222, 31.361658], [-7.165833, 31.368694], [-7.159996, 31.366935],
    [-7.14592,  31.370746], [-7.135277, 31.367228], [-7.118111, 31.37397],
    [-7.102661, 31.378074], [-7.061119, 31.370453], [-7.053223, 31.361951],
    [-7.039146, 31.363417], [-7.025414, 31.338202], [-7.002754, 31.336736],
    [-6.969452, 31.340255], [-6.971855, 31.328232], [-6.979065, 31.325006],
    [-6.990395, 31.313274], [-7.023354, 31.279537], [-7.03743,  31.278656],
    [-7.049446, 31.284525], [-7.059746, 31.277483], [-7.074509, 31.280417],
    [-7.082062, 31.268093], [-7.106094, 31.274842], [-7.108841, 31.28071],
    [-7.124977, 31.283644], [-7.14077,  31.280417], [-7.152786, 31.281004],
]

# --- 4. DATASET FILENAMES ---
LAYERS = {
    "buildings":  "osm_buildings.geojson",
    "roads":      "osm_roads.geojson",
    "pois":       "osm_pois.geojson",
    "population": "worldpop_ounila.tif",
}

# --- 5. SCENARIO MANAGER (Person A's rasters) ---
SCENARIOS = {
    "T10":  {"depth": "depth_T10.tif",  "vel": "velocity_T10.tif",  "label": "10-Year",  "return_period": 10},
    "T50":  {"depth": "depth_T50.tif",  "vel": "velocity_T50.tif",  "label": "50-Year",  "return_period": 50},
    "T100": {"depth": "depth_T100.tif", "vel": "velocity_T100.tif", "label": "100-Year", "return_period": 100},
    "T500": {"depth": "depth_T500.tif", "vel": "velocity_T500.tif", "label": "500-Year", "return_period": 500},
}

# --- 6. ANALYSIS PARAMETERS ---
PARAMS = {
    "debris_factor": 0.5,    # HR Wallingford debris factor (rocky catchment)
    "flood_min_m":   0.1,    # Minimum depth to count as "flooded"
    "risk_levels": {
        "medium": 1.25,      # HR score thresholds
        "high":   2.0,
    },
    # Road passability thresholds (FHWA HEC HIF-12-024)
    "road_passable_m":    0.3,   # Cars can pass below this depth
    "road_emergency_m":  0.6,   # Emergency vehicles only below this depth
    # Composite Risk Index weights (Papathoma-Köhle et al. 2019)
    "cri_weights": {"hazard": 0.5, "exposure": 0.3, "vulnerability": 0.2},
    # Vulnerability proxy for rural semi-arid Morocco
    "vuln_default": 0.3,
    # Citizen signal fusion weight (Poser & Dransch 2010)
    "citizen_weight": 0.3,
}

# --- 7. EARLY WARNING THRESHOLDS (mm/24h forecast rainfall → alert level) ---
# Calibrated from peak discharges in hydrograph CSVs:
#   Green  < T10 event  → routine monitoring
#   Yellow ~ T10        → watch
#   Orange ~ T50        → warning (prepare to act)
#   Red    >= T100      → emergency (act now)
ALERT_THRESHOLDS = {
    "green":  0,
    "yellow": 30,    # ~T10 onset rainfall
    "orange": 55,    # ~T50
    "red":    80,    # ~T100+
}

# --- 8. VULNERABILITY WEIGHTS BY BUILDING TYPE ---
# Used in exposure analysis: critical infrastructure scores highest
VULN_WEIGHTS = {
    "hospital":      3.0,
    "clinic":        3.0,
    "school":        2.5,
    "fire_station":  2.5,
    "residential":   2.0,
    "commercial":    1.5,
    "default":       1.0,
}

# --- 9. API ---
API_PORT = 8000
DB_PATH  = os.path.join(DATA_DB, "citizen_reports.db")