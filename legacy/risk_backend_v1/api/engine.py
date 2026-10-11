import numpy as np


class HydrologyEngine:

    def __init__(self):
        pass

    def compute_curve_number(self, ndvi_matrix):
        """
        Converts the vegetation map (NDVI) into Curve Number (CN).
        CN values: 100 (Impermeable/Rock), ~30 (Dense forest that
        """
        # Base logic: Less vegetation = higher CN (more runoff)
        cn_matrix = np.where(ndvi_matrix < 0.1, 90,   # Roca/Suelo desnudo
                np.where(ndvi_matrix < 0.3, 75,   # Arbustos esparcidos
                np.where(ndvi_matrix < 0.6, 60,   # Normal vegetation
                40)))                             # Dense Forest
        return cn_matrix


    def run_hec_hms_scs(self, P_matrix: np.ndarray, CN_matrix: np.ndarray) -> np.ndarray:
      """
        Execute the model HEC-HMS (SCS Curve Number Method).
        Inputs:
          - P_matrix: Matrix with precipitation in mm.
          - CN_matrix: Matrix with the Curve Number.
        Output:
          - Q_matrix: Matrix with the Runoff (water that doesn't get absorbed and flows down
        """
    
      
      print("Executing HEC-HMS simulation (Runoff)...")
      
      # 1. Calcular 'S' (Retención potencial máxima del suelo)
      # Protegemos contra división por cero por si CN es 0
      CN_safe = np.where(CN_matrix == 0, 0.001, CN_matrix)
      S_matrix = (25400.0 / CN_safe) - 254.0
      
      # 2. Calcular 'Ia' (Abstracción inicial: agua que se queda en charcos o se evapora rápido)
      Ia_matrix = 0.2 * S_matrix
      
      # 3. Calcular 'Q' (Escorrentía directa en mm)
      # Condición: Si llueve menos que Ia, el suelo se lo traga todo y Q = 0.
      # Si llueve más que Ia, aplicamos la fórmula polinómica.
      Q_matrix = np.where(
          P_matrix > Ia_matrix,
          ((P_matrix - Ia_matrix)**2) / (P_matrix + 0.8 * S_matrix),
          0.0
      )
      
      return Q_matrix
    
    def calcular_riesgo_total(self, q_matrix, pendiente_matrix):
      """Cruza el volumen de agua con la inclinación del terreno"""
      # Normalizamos la pendiente para que sea un multiplicador (ej. de 0 a 1)
      pendiente_norm = pendiente_matrix / np.max(pendiente_matrix)
    
      # El riesgo es el agua (Q) multiplicada por la fuerza de la gravedad (pendiente)
      riesgo = q_matrix * (1 + pendiente_norm)
      return riesgo
    

    def calcular_riesgo_erosion_rusle(self, P_matrix, pendiente_matrix, ndvi_matrix):
      """
      Calcula la pérdida de suelo usando la Ecuación RUSLE adaptada
      A = R * K * LS * C * P
      """
      print("🍂 Ejecutando motor de erosión RUSLE (Basado en datos de Sentinel)...")
    
      # 1. Factor R (Lluvia / Erosividad):
      # Simplificamos asumiendo que el impacto es directamente proporcional al volumen de lluvia
      R = P_matrix * 0.35 
    
      # 2. Factor C (Vegetación): ¡EL CÓDIGO DE TU COMPAÑERO!
      # Evitamos que NDVI sea 1 o menor que 0 para no romper la matemática (división por cero)
      ndvi_seguro = np.clip(ndvi_matrix, 0.01, 0.99)
      C = np.exp(-2.0 * (ndvi_seguro / (1.0 - ndvi_seguro)))
    
      # 3. Factor LS (Longitud e Inclinación de la ladera):
      # Usamos tu matriz de pendiente normalizada como un proxy rápido del peligro gravitacional
      LS = pendiente_matrix / (np.max(pendiente_matrix) + 0.001)
    
      # 4. Factor K (Erosionabilidad del suelo) y P (Prácticas de conservación):
      # K: Asumimos un suelo estándar de montaña árida (0.05)
      # P: Asumimos que no hay diques ni terrazas construidas (1.0)
      K = 0.05
      P = 1.0
    
      # LA GRAN ECUACIÓN
      matriz_erosion_A = R * K * LS * C * P
    
      return matriz_erosion_A
    

    def simular_hec_ras_2d(self, matriz_runoff_mm, elevacion_matrix, ndvi_matrix, pendiente_matrix):
        """
        Simulador Hidrodinámico 2D simplificado (Basado en Manning y Gradientes).
        Devuelve: Magnitud de la velocidad y Vectores de dirección.
        """
        print("🌊 Iniciando simulación HEC-RAS 2D (Cinemática y Direcciones)...")
        
        # 1. Calcular Calado (Profundidad del agua en metros)
        # HEC-HMS nos dio el Runoff en mm. Lo pasamos a metros.
        # Si el calado es casi 0, evitamos errores matemáticos sumando un epsilon
        calado_m = (matriz_runoff_mm / 1000.0) + 0.0001
        
        # 2. Mapear Rugosidad de Manning (n) usando el NDVI
        # Asfalto/Roca (NDVI < 0.1) -> n = 0.03 (Rápido)
        # Tierra seca (NDVI < 0.3) -> n = 0.05
        # Vegetación / Bosque (NDVI >= 0.3) -> n = 0.10 (Lento, frena el agua)
        n_matrix = np.where(ndvi_matrix < 0.1, 0.03,
                  np.where(ndvi_matrix < 0.3, 0.05, 0.10))
        
        # 3. Ecuación de Manning para la Magnitud de Velocidad (m/s)
        # v = (1/n) * (Rh^(2/3)) * (S^(1/2))
        # S = pendiente_matrix (tiene que estar en m/m, asumiendo que ya es tangencial)
        S_raiz = np.sqrt(pendiente_matrix)
        velocidad_magnitud = (1.0 / n_matrix) * (calado_m ** (2/3)) * S_raiz
        
        # Limitar velocidades absurdas (en la naturaleza es raro ver agua a más de 15 m/s)
        velocidad_magnitud = np.clip(velocidad_magnitud, 0, 15.0)
        
        # 4. Calcular Dirección del Flujo (Vectores U y V)
        # Usamos el gradiente de elevación. El agua huye de los altos y va a los bajos.
        dy, dx = np.gradient(elevacion_matrix)
        
        # Angulo de caída (dirección del agua). Invertimos el signo porque el agua baja, no sube.
        angulo_flujo = np.arctan2(-dy, -dx)
        
        # Descomponemos la velocidad en sus componentes cardinales
        vector_U = velocidad_magnitud * np.cos(angulo_flujo) # Movimiento Este-Oeste
        vector_V = velocidad_magnitud * np.sin(angulo_flujo) # Movimiento Norte-Sur
        
        return velocidad_magnitud, vector_U, vector_V, angulo_flujo
        

# ==========================================
# CÓMO USARLO EN TU SCRIPT PRINCIPAL
# ==========================================
# Asumiendo que tienes P_matrix y ndvi_matrix de la API:

# 1. Calculas el Curve Number
# CN_matrix = compute_curve_number(ndvi_matrix)

# 2. Ejecutas el motor HEC-HMS
# runoff_matrix = run_hec_hms_scs(P_matrix, CN_matrix)

# print(f"Agua máxima fluyendo en un píxel: {np.max(runoff_matrix):.2f} mm")