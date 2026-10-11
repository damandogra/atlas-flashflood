import rasterio
from rasterio.transform import from_bounds
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

def exportar_geotiff(matrix, filename, bbox_coords, crs="EPSG:4326"):
    """
    Exporta una matriz NumPy a un archivo GeoTIFF con georreferenciación.
    bbox_coords debe ser [min_lon, min_lat, max_lon, max_lat]
    """
    # Evitamos NaNs (los convertimos a 0 para que los programas GIS no den error)
    matrix_safe = np.nan_to_num(matrix)
    
    height, width = matrix_safe.shape
    
    # Creamos el 'Transform' (El mapa que le dice al archivo cuánto mide cada píxel)
    min_lon, min_lat, max_lon, max_lat = bbox_coords
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, width, height)
    
    # Escribimos el archivo
    with rasterio.open(
        filename,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=1,                  # 1 banda (escala de grises/valores)
        dtype=matrix_safe.dtype,
        crs=crs,
        transform=transform,
    ) as dst:
        dst.write(matrix_safe, 1)
        
    print(f"💾 GeoTIFF guardado con éxito: {filename}")
    

def export_erosion_png(erosion_matrix, output_path):
    """
    Convierte la matriz de erosión RUSLE en un PNG transparente (Mapa de calor)
    con auto-escalado dinámico.
    """
    print("🎨 Generando textura PNG para el riesgo de erosión...")
    
    # 1. Chivato para ver qué valores estamos manejando realmente
    max_val = np.nanmax(erosion_matrix)
    mean_val = np.nanmean(erosion_matrix)
    print(f"   📊 Valores RUSLE -> Máximo: {max_val:.4f}, Media: {mean_val:.4f}")
    
    # 2. Escala dinámica (Hackathon pro-tip)
    # Evitamos que un solo píxel loco rompa la escala cogiendo el percentil 95
    vmax_dynamic = np.nanpercentile(erosion_matrix, 95)
    
    # Si por algún motivo la matriz está vacía o es 0, forzamos un valor para que no crashee
    if vmax_dynamic <= 0:
        vmax_dynamic = 1.0 
        
    vmin_dynamic = vmax_dynamic * 0.15 # El umbral será el 15% del valor más alto

    # 3. Aplicar colores
    erosion_clipped = np.clip(erosion_matrix, vmin_dynamic, vmax_dynamic)
    cmap = plt.cm.get_cmap('YlOrRd')
    norm = Normalize(vmin=vmin_dynamic, vmax=vmax_dynamic) 
    
    rgba_img = cmap(norm(erosion_clipped))
    
    # 4. Transparencia: Ocultamos solo el 15% más bajo (zonas seguras)
    alpha_channel = np.where(erosion_matrix < vmin_dynamic, 0.0, 0.65)
    rgba_img[..., 3] = alpha_channel
    
    # 5. Guardar
    plt.imsave(output_path, rgba_img, format='png')
    print(f"✅ Capa de erosión guardada en: {output_path}")