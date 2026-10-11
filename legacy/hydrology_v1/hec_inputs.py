import os
import math
import numpy as np
import matplotlib.pyplot as plt
from dotenv import load_dotenv

from sentinelhub import (
    SHConfig,
    SentinelHubRequest,
    DataCollection,
    MimeType
)

# Local imports
from coordinates import Coordinates, roi_bbox
from get_precipitation import get_precipitation_data
from evalscripts import NDVI
from engine import HydrologyEngine
from export import exportar_geotiff, export_erosion_png

load_dotenv() 

# ==========================================
# 1. CONFIGURATION & AUTHENTICATION
# ==========================================
config = SHConfig()
config.sh_client_id = os.getenv('SH_CLIENT_ID')
config.sh_client_secret = os.getenv('SH_CLIENT_SECRET')
config.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
config.sh_base_url = "https://sh.dataspace.copernicus.eu"

CDSE_S2_L2A = DataCollection.define("CDSE_S2_L2A", api_id=DataCollection.SENTINEL2_L2A.api_id, service_url=config.sh_base_url)
CDSE_DEM = DataCollection.define("CDSE_DEM", api_id=DataCollection.DEM_COPERNICUS_30.api_id, service_url=config.sh_base_url)


# ==========================================
# 2. GEOMETRY & RESOLUTION (Square Pixels)
# ==========================================
# Get bounding box coordinates from the polygon
min_lon, min_lat, max_lon, max_lat = roi_bbox.geometry.bounds
geotiff_coords = [min_lon, min_lat, max_lon, max_lat]
print("📍 COORDENADAS PARA REACT BBOX:")
print(f"min_lon={min_lon}, min_lat={min_lat}, max_lon={max_lon}, max_lat={max_lat}")

# Calculate distance in degrees
delta_lon = max_lon - min_lon
delta_lat = max_lat - min_lat

# Trigonometric correction factor for Earth's curvature
aspect_ratio = (delta_lon * math.cos(math.radians((min_lat + max_lat) / 2))) / delta_lat

# Set width to 1000 pixels and calculate proportional height
width_px = 1000
height_px = int(width_px / aspect_ratio)
img_size = (width_px, height_px)

print(f"📏 Corrected resolution for square pixels: {img_size}")


# ==========================================
# 3. PRECIPITATION & ENGINE SETUP
# ==========================================
coordinates = Coordinates(lat=31.3, lon=-7.31)
precipitation_data = get_precipitation_data(coordinates)
print(f"🌦️ Real rain today (Open-Meteo): {precipitation_data} mm")

hydro_engine = HydrologyEngine()


# ==========================================
# 4. FETCH SATELLITE DATA (NDVI & DEM)
# ==========================================
print("🛰️ Downloading NDVI map from Sentinel-2...")
request_ndvi = SentinelHubRequest(
    evalscript=NDVI,
    input_data=[SentinelHubRequest.input_data(data_collection=CDSE_S2_L2A, time_interval=("2024-04-01", "2024-04-24"))],
    responses=[SentinelHubRequest.output_response('default', MimeType.TIFF)],
    bbox=roi_bbox,
    size=img_size,
    config=config
)
ndvi_matrix = request_ndvi.get_data()[0]

# --- HACKATHON MODE: SIMULATE EXTREME STORM ---
SIMULATED_STORM_MM = 120.0
# Fix: Initialize using ndvi_matrix.shape to ensure NumPy matrices align perfectly
precipitation_matrix = np.full(ndvi_matrix.shape, SIMULATED_STORM_MM)

# Compute Curve Number (CN)
cn_matrix = hydro_engine.compute_curve_number(ndvi_matrix)
print("✅ Curve Number (CN) matrix calculated.")


print("🛰️ Downloading Digital Elevation Model (Copernicus DEM)...")
evalscript_dem = """
//VERSION=3
function setup() {
    return { input: ["DEM"], output: { bands: 1, sampleType: "FLOAT32" } };
}
function evaluatePixel(sample) {
    return [sample.DEM];
}
"""
request_dem = SentinelHubRequest(
    evalscript=evalscript_dem,
    input_data=[SentinelHubRequest.input_data(data_collection=CDSE_DEM)],
    responses=[SentinelHubRequest.output_response('default', MimeType.TIFF)],
    bbox=roi_bbox,
    size=img_size,
    config=config
)
elevation_matrix = request_dem.get_data()[0]

# Calculate Slope using NumPy's spatial gradient
dy, dx = np.gradient(elevation_matrix)
slope_matrix = np.sqrt(dx**2 + dy**2)
print("✅ Elevation and Slope matrices calculated.")

print("-" * 30)
print("⚙️ PRE-PROCESSING COMPLETED!")
print(f"Matrix shapes: P={precipitation_matrix.shape}, CN={cn_matrix.shape}, Slope={slope_matrix.shape}")


# ==========================================
# 5. HYDROLOGY ENGINE (Baseline)
# ==========================================
print("🚀 Starting Hydrology Engine...")
runoff_matrix = hydro_engine.run_hec_hms_scs(precipitation_matrix, cn_matrix)

# Note: Ensure the method name in engine.py matches 'calcular_riesgo_total' or update it here if you translated it.
risk_matrix = hydro_engine.calcular_riesgo_total(runoff_matrix, slope_matrix) 

print(f"✅ Baseline HEC-HMS completed! Max runoff detected: {np.max(runoff_matrix):.2f} mm")


# ==========================================
# 6. RISK ASSESSMENT SCENARIOS (GeoTIFF Export)
# ==========================================
# Replaced with GEV actual data
rainfall_scenarios = {
    'T10': 23.7,
    'T50': 36.3,
    'T100': 43.9,
    'T500': 68.8
}

print("🏭 Starting scenario generation for Risk Assessment...")

for return_period, rain_mm in rainfall_scenarios.items():
    print(f"\n--- Processing Scenario {return_period} ({rain_mm} mm) ---")
    
    # A. Create precipitation matrix for this scenario using correct shape
    scenario_p_matrix = np.full(ndvi_matrix.shape, rain_mm)
    
    # B. Recalculate Runoff (HEC-HMS)
    scenario_runoff_mm = hydro_engine.run_hec_hms_scs(scenario_p_matrix, cn_matrix)
    depth_meters = scenario_runoff_mm / 1000.0
    
    # C. Recalculate Velocity (Simplified HEC-RAS 2D)
    # Note: Update method name 'simular_hec_ras_2d' if you translated it in engine.py
    velocity, vector_u, vector_v, angle = hydro_engine.simular_hec_ras_2d(
        scenario_runoff_mm, elevation_matrix, ndvi_matrix, slope_matrix
    )
    
    # D. Export GeoTIFFs
    depth_filename = f"depth_{return_period}.tif"
    velocity_filename = f"velocity_{return_period}.tif"
    flow_direction_filename = f"flow_direction_{return_period}.tif"
    
    exportar_geotiff(depth_meters, depth_filename, geotiff_coords)
    exportar_geotiff(velocity, velocity_filename, geotiff_coords)
    exportar_geotiff(angle, flow_direction_filename, geotiff_coords)

print("\n✅ Data batch completed successfully!")

np.save("ndvi_base.npy", ndvi_matrix)
np.save("dem_base.npy", elevation_matrix)
np.save("slope_base.npy", slope_matrix)
exportar_geotiff(ndvi_matrix, "ndvi_base.tif", geotiff_coords)
print("⛰️ Calculando Riesgo de Erosión (RUSLE)...")

# Llamas a tu función (asegúrate de que los parámetros coinciden con tu código)
# Asumimos que hydro_engine.calcular_rusle() devuelve una matriz NumPy
erosion_matrix = hydro_engine.calcular_riesgo_erosion_rusle(
    precipitation_matrix,   # Lluvia (R)
    slope_matrix,    # Relieve (LS)
    ndvi_matrix      # Vegetación (C)
)

export_erosion_png(erosion_matrix, "erosion_rusle.png")