import osmnx as ox
import geopandas as gpd
from shapely.geometry import Polygon
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

def download_osm_data():
    """Downloads OSM layers using geometry defined in config.py"""
    # 1. Build Study Area from Config
    poly = Polygon(config.CATCHMENT_COORDS)
    gdf = gpd.GeoDataFrame(index=[0], geometry=[poly], crs=config.GEO_CRS)
    
    # Apply Buffer from Config
    buffer_geom = gdf.to_crs(config.PROJ_CRS).geometry.buffer(config.BUFFER_M).to_crs(config.GEO_CRS).iloc[0]

    # 2. Buildings
    print("🛰️ Downloading buildings...")
    buildings = ox.features_from_polygon(buffer_geom, tags={"building": True}).reset_index()
    buildings.to_file(os.path.join(config.DATA_RAW, config.LAYERS["buildings"]), driver="GeoJSON")

    # 3. Roads
    print("🛣️ Downloading roads...")
    G = ox.graph_from_polygon(buffer_geom, network_type="drive", simplify=True)
    edges = ox.graph_to_gdfs(G, nodes=False, edges=True)
    edges.to_file(os.path.join(config.DATA_RAW, config.LAYERS["roads"]), driver="GeoJSON")

    # 4. POIs
    print("🏥 Downloading POIs...")
    tags = {"amenity": ["hospital", "school", "clinic", "fire_station"]}
    pois = ox.features_from_polygon(buffer_geom, tags=tags).reset_index()
    pois.to_file(os.path.join(config.DATA_RAW, config.LAYERS["pois"]), driver="GeoJSON")

    print("✅ OSM Ingestion Complete.")