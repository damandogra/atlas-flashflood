import requests
from coordinates import Coordinates
from datetime import datetime

def get_precipitation_data(coordinates: Coordinates):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={coordinates.lat}&longitude={coordinates.lon}&daily=precipitation_sum&timezone=auto"
    response = requests.get(url).json()
    # Cogemos la lluvia prevista para hoy (en mm)
    rain_today = response['daily']['precipitation_sum'][0]
    return rain_today


def get_historical_precipitation_data(coordinates: Coordinates):
    """
    Usa el archivo histórico de Copernicus ERA5 (vía Open-Meteo) 
    para extraer los máximos históricos y simular Periodos de Retorno.
    """
    print("🛰️ Consultando satélites Copernicus ERA5-Land...")
    
    # Pedimos datos desde 1940 (Límite de ERA5) hasta hoy
    url = (f"https://archive-api.open-meteo.com/v1/archive?"
           f"latitude={coordinates.lat}&longitude={coordinates.lon}&"
           f"start_date=1940-01-01&end_date=2026-04-25&"
           f"daily=precipitation_sum&timezone=auto")
    
    try:
        response = requests.get(url).json()
        fechas = response['daily']['time']
        lluvias = response['daily']['precipitation_sum']
        
        # Juntar fechas y lluvias, ignorando valores nulos
        datos_historicos = [(f, l) for f, l in zip(fechas, lluvias) if l is not None]
        
        # Función auxiliar para sacar el máximo en un rango de años
        def max_in_years(max_years):
            limit_year = 2026 - max_years
            lluvias_filtradas = [l for f, l in datos_historicos if int(f[:4]) >= limit_year]
            return max(lluvias_filtradas) if lluvias_filtradas else 0

        # Calcular los equivalentes estadísticos
        t10_real = max_in_years(10)
        t50_real = max_in_years(50)
        t100_proxy = max_in_years(84) # Máximo absoluto de la serie de ERA5
        
        # Para el T500 (evento apocalíptico), la regla empírica suele ser añadir un 30-40% al T100
        t500_estimado = round(t100_proxy * 1.35, 1)

        print("\n📊 --- DATOS COPERNICUS ERA5 PARA TIGHZA ---")
        print(f"T10  (Max en 10 años):  {t10_real} mm")
        print(f"T50  (Max en 50 años):  {t50_real} mm")
        print(f"T100 (Max desde 1940):  {t100_proxy} mm")
        print(f"T500 (Extrapolación):   {t500_estimado} mm")
        
        return {"T10": t10_real, "T50": t50_real, "T100": t100_proxy, "T500": t500_estimado}

    except Exception as e:
        print(f"Error extrayendo datos de ERA5: {e}")
        return None


