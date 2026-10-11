import rasterio
import numpy as np
from sentinelhub import BBox, CRS, Geometry

"""
# Coordinates for Tighza, Morocco
# Tighza (Mountain/Peak, Atlas):
latitude = -5.62389000
longitude = 33.18750000
"""

polygon_coordinates = [
    [
        [-7.152786, 31.281004], [-7.173386, 31.285698], 
        [-7.185402, 31.28159], [-7.188835, 31.293033], 
        [-7.171326, 31.29626], [-7.181625, 31.307407], 
        [-7.172356, 31.31386], [-7.179909, 31.337616], 
        [-7.175789, 31.351397], [-7.179222, 31.361658], 
        [-7.165833, 31.368694], [-7.159996, 31.366935], 
        [-7.14592, 31.370746], [-7.135277, 31.367228], 
        [-7.118111, 31.37397], [-7.102661, 31.378074], 
        [-7.061119, 31.370453], [-7.053223, 31.361951], 
        [-7.039146, 31.363417], [-7.025414, 31.338202], 
        [-7.002754, 31.336736], [-6.969452, 31.340255], 
        [-6.971855, 31.328232], [-6.979065, 31.325006], 
        [-6.990395, 31.313274], [-7.023354, 31.279537], 
        [-7.03743, 31.278656], [-7.049446, 31.284525], 
        [-7.059746, 31.277483], [-7.074509, 31.280417], 
        [-7.082062, 31.268093], [-7.106094, 31.274842], 
        [-7.108841, 31.28071], [-7.124977, 31.283644], 
        [-7.14077, 31.280417], [-7.152786, 31.281004]  # close the ring — repeat first point
    ]
]

anillo_principal = polygon_coordinates[0]

# 1. Extraer min/max para el Bounding Box
lons = [c[0] for c in anillo_principal]
lats = [c[1] for c in anillo_principal]

min_lon, max_lon = min(lons), max(lons)
min_lat, max_lat = min(lats), max(lats)

# Crear el BBox oficial para tus peticiones

roi_bbox = BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)

print(f"BBox calculado: {roi_bbox}")

# 2. Crear el objeto Geometría (útil para que la API recorte el TIF automáticamente)
roi_geometry = Geometry(
    geometry={'type': 'Polygon', 'coordinates': polygon_coordinates}, 
    crs=CRS.WGS84
)


class Coordinates:
    lat: float
    lon: float
    def __init__(self, lat, lon):
        self.lat = lat
        self.lon = lon