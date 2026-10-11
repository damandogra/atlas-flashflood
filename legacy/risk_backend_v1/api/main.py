"""
api/main.py
===========
Issue #18 — FastAPI backend serving all 9 endpoints.

All endpoints:
  GET  /scenarios         → list of available return periods
  GET  /exposure/{ts}     → GeoJSON of flooded buildings
  GET  /roads/{ts}        → GeoJSON of roads with passability
  GET  /risk/{ts}         → CRI raster stats (GeoTIFF served as stream)
  GET  /alert             → current alert level (live Open-Meteo)
  GET  /citizen           → all community observations as GeoJSON
  POST /citizen           → submit a new observation
  GET  /action_cards      → ranked planner actions
  GET  /docs              → auto-generated Swagger UI (FastAPI built-in)

Start:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import sys
import time
import subprocess
import json
import math
import numpy as np
import rasterio
from pathlib import Path
from typing import Optional


from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from .engine import HydrologyEngine
from .export import exportar_geotiff

# ---------------------------------------------------------------------------
# Path setup — allow running from the api/ subdirectory or project root
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
sys.path.insert(0, _ROOT)

import config

# Late imports of project modules (same path tricks applied above)
from scripts import e_citizen as citizen_store
from scripts import g_action_generator
from scripts import d_early_warning


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Ounila Flood Decision System API",
    description=(
        "Flood risk data for the Ounila River catchment, Tighza, Morocco. "
        "Provides scenario exposure, road passability, risk index, live early "
        "warning, and community observations."
    ),
    version="1.0.0",
)

# CORS — allow the React frontend (Vite default port) and any localhost origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure DB exists on startup
citizen_store.init_db()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ObservationIn(BaseModel):
    lat:         float = Field(..., ge=-90,  le=90,  description="Latitude (WGS84)")
    lon:         float = Field(..., ge=-180, le=180, description="Longitude (WGS84)")
    event_type:  str   = Field(..., description="One of: flooding, road_blocked, structure_damage, evacuation_needed, infrastructure_damage, other")
    severity:    int   = Field(..., ge=1,   le=3,   description="1=minor, 2=moderate, 3=severe")
    description: str   = Field("",  description="Free-text description")
    reporter:    str   = Field("anonymous")
    
class DynamicSimulationIn(BaseModel):
    rainfall_mm: float = Field(..., description="Milímetros exactos del slider")
    is_planting: bool = Field(False, description="¿Hay intervención NBS?")
    lat: Optional[float] = None
    lon: Optional[float] = None
    radius_m: float = 500.0

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _valid_scenario(ts: str) -> str:
    """Normalise and validate a scenario key, allowing CUSTOM cache-busters."""
    ts_up = ts.upper()
    
    # EL TRUCO CACHE-BUSTER: Si empieza por CUSTOM, usamos los archivos CUSTOM
    if ts_up.startswith("CUSTOM"):
        return "CUSTOM"
        
    if ts_up not in config.SCENARIOS.keys():
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scenario '{ts}'. Valid: {list(config.SCENARIOS.keys())} or CUSTOM",
        )
    return ts_up


def _load_geojson_safe(path: str) -> dict:
    """Carga un GeoJSON, pero si no existe devuelve uno vacío en lugar de explotar."""
    if not os.path.exists(path):
        return {"type": "FeatureCollection", "features": []}
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/scenarios", summary="List available flood scenarios")
def get_scenarios():
    available = []
    for ts, info in config.SCENARIOS.items():
        exposure_path = os.path.join(config.DATA_OUT, f"exposure_{ts}.geojson")
        available.append({
            "id":            ts,
            "label":         info.get("label", ts),
            "return_period": info.get("return_period", 0),
            "available":     os.path.exists(exposure_path),
        })
    return {"scenarios": available}


@app.get("/exposure/{scenario}", summary="Flooded buildings for a scenario")
def get_exposure(scenario: str):
    ts   = _valid_scenario(scenario)
    path = os.path.join(config.DATA_OUT, f"exposure_{ts}.geojson")
    return JSONResponse(_load_geojson_safe(path))


@app.get("/roads/{scenario}", summary="Road passability for a scenario")
def get_roads(scenario: str):
    ts   = _valid_scenario(scenario)
    path = os.path.join(config.DATA_OUT, f"road_passability_{ts}.geojson")
    return JSONResponse(_load_geojson_safe(path))

@app.get("/flow/{scenario}", summary="Flow direction vectors for a scenario")
def get_flow(scenario: str):
    ts = _valid_scenario(scenario)
    path = os.path.join(config.DATA_OUT, f"flow_arrows_{ts}.geojson")
    return JSONResponse(_load_geojson_safe(path))

@app.get("/risk/{scenario}", summary="CRI raster stats for a scenario")
def get_risk(scenario: str, fused: bool = Query(False, description="Use citizen-fused CRI if available")):
    ts = _valid_scenario(scenario)
    
    # Parche Zombie para CUSTOM: devolvemos un diccionario de stats vacío para que no rompa las gráficas
    if ts == "CUSTOM":
        return {"hazard_mean": 0, "exposure_mean": 0, "vulnerability_mean": 0, "cri_mean": 0}

    summary_path = os.path.join(config.DATA_OUT, "cri_summary.json")
    if os.path.exists(summary_path):
        with open(summary_path) as f:
            all_summary = json.load(f)
        if ts in all_summary:
            return all_summary[ts]

    # Si nos piden otro y no está, mandamos un error suave
    return JSONResponse(status_code=200, content={"cri_mean": 0})


@app.get("/risk/{scenario}/download", summary="Download CRI GeoTIFF")
def download_risk(scenario: str, fused: bool = Query(False)):
    ts     = _valid_scenario(scenario)
    prefix = "cri_fused" if fused else "cri"
    path   = os.path.join(config.DATA_OUT, f"{prefix}_{ts}.tif")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="CRI raster not found.")
    return FileResponse(path, media_type="image/tiff", filename=f"{prefix}_{ts}.tif")


@app.get("/alert", summary="Current early warning alert level")
def get_current_alert():
    return d_early_warning.get_alert()


@app.get("/citizen", summary="Community observations as GeoJSON")
def get_citizen_observations(
    event_type:   Optional[str] = Query(None, description="Filter by event type"),
    min_severity: int           = Query(1,    ge=1, le=3, description="Minimum severity"),
):
    return citizen_store.as_geojson(event_type=event_type, min_severity=min_severity)


@app.post("/citizen", summary="Submit a community observation", status_code=201)
def post_citizen_observation(obs: ObservationIn):
    try:
        obs_id = citizen_store.add_observation(
            lat=obs.lat, lon=obs.lon, event_type=obs.event_type,
            severity=obs.severity, description=obs.description, reporter=obs.reporter,
        )
        return {"status": "created", "id": obs_id}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/action_cards", summary="Ranked planner action cards")
def get_action_cards(scenario: str = Query("T100", description="Scenario to generate actions")):
    ts = _valid_scenario(scenario)

    # Parche Zombie para CUSTOM: devolvemos un array vacío
    if ts == "CUSTOM":
        return {"scenario": ts, "count": 0, "cards": []}

    cached_path = os.path.join(config.DATA_OUT, "action_cards.json")
    if os.path.exists(cached_path):
        with open(cached_path) as f:
            cards = json.load(f)
        cards = [c for c in cards if c.get("scenario") == ts]
        if cards:
            return {"scenario": ts, "count": len(cards), "cards": cards}

    cards = g_action_generator.generate_action_cards(ts)
    return {"scenario": ts, "count": len(cards), "cards": cards}
@app.post("/simulate/custom", summary="Dynamic simulation")
def simulate_custom(data: DynamicSimulationIn):
    start_time = time.time()
    
    # 1. Cargar las matrices base vírgenes (Asumiendo que las guardaste en DATA_OUT)
    ndvi_npy_path = os.path.join(config.DATA_TIF, "ndvi_base.npy")
    ndvi_tif_path = os.path.join(config.DATA_TIF, "ndvi_base.tif")
    
    if not os.path.exists(ndvi_npy_path):
        raise HTTPException(status_code=404, detail="Matrices base no encontradas. Ejecuta el engine primero.")

    ndvi = np.load(ndvi_npy_path)
    elevation = np.load(os.path.join(config.DATA_TIF, "dem_base.npy"))
    slope = np.load(os.path.join(config.DATA_TIF, "slope_base.npy"))

    # 2. Inicializar Motor y Lluvia
    engine = HydrologyEngine()
    precip_matrix = np.full(ndvi.shape, data.rainfall_mm)
    
    # 3. Calcular Baseline (Siempre lo necesitamos para comparar el impacto)
    cn_base = engine.compute_curve_number(ndvi)
    runoff_base = engine.run_hec_hms_scs(precip_matrix, cn_base)
    
    reduction_pct = 0.0
    area_ha = 0.0
    
    # 4. Aplicar Intervención (NBS) si hay árboles
    if data.is_planting and data.lat and data.lon:
        with rasterio.open(ndvi_tif_path) as src:
            transform = src.transform
            row, col = src.index(data.lon, data.lat)
            
        pixel_size_m = abs(transform[0]) * 111320.0 * math.cos(math.radians(data.lat))
        radius_px = data.radius_m / pixel_size_m
        
        height, width = ndvi.shape
        y, x = np.ogrid[:height, :width]
        dist_sq = (x - col)**2 + (y - row)**2
        mask = dist_sq <= radius_px**2
        
        ndvi_modified = ndvi.copy()
        ndvi_modified[mask] = 0.85 # Plantar bosque
        
        cn_mitigado = engine.compute_curve_number(ndvi_modified)
        runoff_final = engine.run_hec_hms_scs(precip_matrix, cn_mitigado)
        
        # Calcular reducción
        total_base = np.sum(runoff_base)
        total_mitigado = np.sum(runoff_final)
        if total_base > 0:
            reduction_pct = ((total_base - total_mitigado) / total_base) * 100
        
        area_ha = (np.sum(mask) * (pixel_size_m**2)) / 10000.0
    else:
        # Si no hay árboles, el runoff final es el baseline
        runoff_final = runoff_base

    # 5. Simulación HEC-RAS 2D (Profundidad, Velocidad, Ángulo)
    depth_meters = runoff_final / 1000.0
    # Usamos ndvi_modified si hay bosque, si no el normal
    matriz_veg = ndvi_modified if (data.is_planting and 'ndvi_modified' in locals()) else ndvi
    velocity, u, v, angle = engine.simular_hec_ras_2d(runoff_final, elevation, matriz_veg, slope)

    # 6. Exportar TIFs al directorio DATA_TIF para que el config.py los procese
    bbox_coords = [-7.188835, 31.268093, -6.969452, 31.378074]    
    
    exportar_geotiff(depth_meters, os.path.join(config.DATA_TIF, "depth_CUSTOM.tif"), bbox_coords)
    exportar_geotiff(velocity, os.path.join(config.DATA_TIF, "velocity_CUSTOM.tif"), bbox_coords)
    exportar_geotiff(angle, os.path.join(config.DATA_TIF, "flow_direction_CUSTOM.tif"), bbox_coords)

# 7. Magia Negra: Llamar a los scripts (Rutas corregidas y seguras)
    try:
        # Corregida la ruta: Si config.BASE_DIR es la raíz, no hace falta el ".."
        script_exposure = os.path.join(config.BASE_DIR, "scripts", "b_analyse_exposure.py")
        script_network = os.path.join(config.BASE_DIR, "scripts", "b_analyse_network.py")
        
        print(f"Ejecutando: {script_exposure}") # Chivato en tu consola
        
        # Ejecutamos exposure
        res_exp = subprocess.run([sys.executable, script_exposure, "CUSTOM"], capture_output=True, text=True)
        if res_exp.returncode != 0:
            raise ValueError(f"Error en b_analyse_exposure.py:\n{res_exp.stderr}")

        # Ejecutamos network
        res_net = subprocess.run([sys.executable, script_network, "CUSTOM"], capture_output=True, text=True)
        if res_net.returncode != 0:
            raise ValueError(f"Error en b_analyse_network.py:\n{res_net.stderr}")

    except Exception as e:
        # Esto imprimirá el error real (línea de código que falla, archivo no encontrado, etc.)
        print("💥 ERROR FATAL EN SUBPROCESS:")
        print(str(e))
        raise HTTPException(status_code=500, detail=str(e))
    
    calc_time = round(time.time() - start_time, 1)

    # 8. Respuesta rica para el frontend
    msg = f"Simulation completed in {calc_time}s for {data.rainfall_mm}mm."
    if data.is_planting:
        msg += f" Reforestation ({round(area_ha,1)}ha) applied with {round(reduction_pct, 1)}% reduction."

    return {
        "status": "success",
        "scenario_generated": "CUSTOM",
        "metrics": {
            "rainfall_applied": data.rainfall_mm,
            "nbs_applied": data.is_planting,
            "area_treated_ha": round(area_ha, 2),
            "peak_discharge_reduction_pct": round(reduction_pct, 2),
            "calculation_time_sec": calc_time
        },
        "message": msg
    }
# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "service": "ounila-flood-api"}