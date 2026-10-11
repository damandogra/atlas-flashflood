import os
import requests
import rasterio
from rasterio.mask import mask
import geopandas as gpd
from shapely.geometry import Polygon
import sys

# Standard path fix we discussed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

def run_worldpop_ingestion():
    # 1. Download Setup
    url = "https://data.worldpop.org/GIS/Population/Global_2000_2020/2020/MAR/mar_ppp_2020.tif"
    raw_path = os.path.join(config.DATA_RAW, "worldpop_morocco_raw.tif")
    output_path = os.path.join(config.DATA_RAW, config.LAYERS["population"])
    
    if not os.path.exists(raw_path):
        print("🛰️ Downloading WorldPop Morocco (approx 20MB)...")
        r = requests.get(url, stream=True)
        if r.status_code == 200:
            with open(raw_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        else:
            print(f"❌ Failed to download. Status: {r.status_code}")
            return

    # 2. Clipping Logic
    print("✂️ Clipping population raster to catchment...")
    
    # Create the clipping geometry from config
    poly = Polygon(config.CATCHMENT_COORDS)
    gdf = gpd.GeoDataFrame(index=[0], geometry=[poly], crs=config.GEO_CRS)
    # Apply the buffer defined in config (25km)
    buffer_gdf = gdf.to_crs(config.PROJ_CRS)
    buffer_gdf.geometry = buffer_gdf.geometry.buffer(config.BUFFER_M)
    clip_geom = buffer_gdf.to_crs(config.GEO_CRS).geometry

    with rasterio.open(raw_path) as src:
        out_image, out_transform = mask(src, clip_geom, crop=True)
        out_meta = src.meta.copy()

    # Update metadata for the clipped version
    out_meta.update({
        "driver": "GTiff",
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform
    })

    # 3. Save the final file
    with rasterio.open(output_path, "w", **out_meta) as dest:
        dest.write(out_image)

    print(f"✅ Population data ready: {output_path}")

if __name__ == "__main__":
    run_worldpop_ingestion()