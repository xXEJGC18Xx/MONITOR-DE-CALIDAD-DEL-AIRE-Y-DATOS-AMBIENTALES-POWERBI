"""
exportar_powerbi.py
===================
Genera las 6 tablas del modelo estrella a partir de los datos procesados
del pipeline y las exporta a un unico Excel para Power BI.

Tablas generadas (una por hoja):
    - fact_lecturas     : lecturas de calidad del aire + clima
    - dim_ciudad        : ciudades con pais, latitud, longitud
    - dim_tiempo        : fechas, horas, dias, meses
    - dim_categoria_aqi : categorias AQI segun EPA
    - fact_predicciones : pronostico PM2.5 a 24h por ciudad
    - fact_resumenes    : resumen diario generado por LLM

Ejecutar con:
    python exportar_powerbi.py
"""

import glob
import logging
from pathlib import Path

import pandas as pd

from config import (
    CIUDADES,
    CSV_PROCESADO,
    PAIS_POR_CIUDAD,
    PROCESSED_DIR,
    UMBRALES_AQI,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# Mapeo de variantes de nombre de ciudad que aparecen en los datos crudos
# hacia el nombre canonico definido en config.py.
# Esto asegura que el JOIN en Power BI funcione correctamente.
MAPEO_NOMBRES_CIUDAD = {
    "Panama City": "Ciudad de Panamá",
    "Santiago": "Santiago de Chile",
    "Guadalajara (M\u00e9xico)": "Guadalajara",
    "Sao Paulo": "S\u00e3o Paulo",
    "Bogota": "Bogot\u00e1",
    "Asuncion": "Asunci\u00f3n",
    "Sao Jose": "San Jos\u00e9",
}


def normalizar_ciudad(nombre):
    """Devuelve el nombre canonico de una ciudad segun config.py."""
    if not isinstance(nombre, str):
        return nombre
    return MAPEO_NOMBRES_CIUDAD.get(nombre, nombre)


def _leer_datos_procesados():
    """Carga el CSV procesado y normaliza timestamp + nombres de ciudad."""
    if not CSV_PROCESADO.exists():
        raise FileNotFoundError(
            f"No existe {CSV_PROCESADO}. Ejecute primero el pipeline."
        )
    df = pd.read_csv(CSV_PROCESADO)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["ciudad"] = df["ciudad"].apply(normalizar_ciudad)
    return df


def construir_fact_lecturas(df):
    """Tabla de hechos principal: mediciones con FK a las dimensiones."""
    columnas = [
        "ciudad", "timestamp",
        "aqi", "aqi_reportado",
        "pm25", "pm10", "co", "o3", "no2", "so2",
        "temperatura", "humedad", "temperatura_aparente",
        "viento_kmh", "precipitacion_mm", "codigo_clima",
        "categoria_aqi",
    ]
    disponibles = [c for c in columnas if c in df.columns]
    fact = df[disponibles].copy()

    # Columna fecha para relacionar con dim_tiempo (sin hora).
    fact["fecha"] = fact["timestamp"].dt.date
    return fact


def construir_dim_ciudad():
    """Dimension de ciudades: catalogo maestro desde config.py."""
    dim = pd.DataFrame([
        {
            "ciudad":   nombre,
            "pais":     PAIS_POR_CIUDAD.get(nombre, "Otros"),
            "latitud":  cfg["lat"],
            "longitud": cfg["lon"],
            "waqi_id":  cfg["waqi_id"],
        }
        for nombre, cfg in CIUDADES.items()
    ])
    return dim


def construir_dim_tiempo(df):
    """Dimension de tiempo: fechas unicas con atributos calendario."""
    dim = df[["timestamp"]].drop_duplicates().copy()
    dim = dim.dropna(subset=["timestamp"]).reset_index(drop=True)
    dim["fecha"]         = dim["timestamp"].dt.date
    dim["timestamp_str"] = dim["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    dim["hora"]          = dim["timestamp"].dt.hour
    dim["dia"]           = dim["timestamp"].dt.day
    dim["dia_semana"]    = dim["timestamp"].dt.dayofweek
    dim["nombre_dia"]    = dim["timestamp"].dt.day_name()
    dim["es_fin_semana"] = (dim["dia_semana"] >= 5).astype(int)
    dim["semana"]        = dim["timestamp"].dt.isocalendar().week.astype(int)
    dim["mes"]           = dim["timestamp"].dt.month
    dim["nombre_mes"]    = dim["timestamp"].dt.month_name()
    dim["year"]          = dim["timestamp"].dt.year
    return dim


def construir_dim_categoria_aqi():
    """Dimension de categorias AQI: rangos EPA con etiqueta, color y riesgo."""
    dim = pd.DataFrame([
        {
            "categoria_aqi": v["etiqueta"],
            "color_aqi":     v["color"],
            "riesgo_salud":  v["riesgo"],
            "aqi_min":       k[0],
            "aqi_max":       k[1],
        }
        for k, v in UMBRALES_AQI.items()
    ])
    return dim


def construir_fact_predicciones():
    """Tabla de hechos de predicciones: lee todos los predicciones_*.csv y
    agrega la columna ciudad extraida del nombre del archivo."""
    archivos = sorted(glob.glob(str(PROCESSED_DIR / "predicciones_*.csv")))
    if not archivos:
        logger.warning("No se encontraron archivos de predicciones.")
        return pd.DataFrame(columns=[
            "ciudad", "hora", "pm25_predicho", "lower", "upper"
        ])

    frames = []
    for ruta in archivos:
        nombre = Path(ruta).stem
        # predicciones_ciudad_de_panama -> Ciudad de Panamá
        ciudad_slug = nombre.replace("predicciones_", "").replace("_", " ")
        # Reemplazar palabras comunes en sus formas correctas
        ciudad = ciudad_slug.replace(" De ", " de ").replace(" Del ", " del ")
        ciudad = ciudad.replace(" La ", " la ").replace(" Las ", " las ")
        # Capitalizar la primera letra de cada palabra
        ciudad = " ".join(p.capitalize() for p in ciudad.split())
        # Tildes en casos conocidos
        ciudad = ciudad.replace("Bogota", "Bogot\u00e1")
        ciudad = ciudad.replace("Asuncion", "Asunci\u00f3n")
        ciudad = ciudad.replace("Sao Paulo", "S\u00e3o Paulo")
        ciudad = ciudad.replace("Sao Jose", "San Jos\u00e9")
        ciudad = ciudad.replace("Medellin", "Medell\u00edn")
        # Casos especificos: "Ciudad De Panama" -> "Ciudad de Panamá"
        ciudad = ciudad.replace("Ciudad De Panam\u00e1", "Ciudad de Panam\u00e1")
        ciudad = ciudad.replace("Ciudad De Mexico", "Ciudad de M\u00e9xico")
        df = pd.read_csv(ruta)
        df["ciudad"] = ciudad
        frames.append(df)

    fact = pd.concat(frames, ignore_index=True)
    return fact


def construir_fact_resumenes():
    """Tabla de hechos con los resumenes diarios generados por el LLM."""
    ruta = PROCESSED_DIR / "resumenes_diarios.csv"
    if not ruta.exists():
        logger.warning(
            "No existe %s. Ejecute el pipeline para generar resumenes.",
            ruta,
        )
        return pd.DataFrame(columns=[
            "fecha", "timestamp_generacion",
            "ciudad_max_aqi", "ciudad_min_aqi",
            "promedio_pm25", "ciudades_sobre_100",
            "resumen_texto",
        ])
    return pd.read_csv(ruta)


def exportar_a_carpeta(tablas, carpeta_salida):
    """Exporta un dict de DataFrames a CSVs individuales en una carpeta.
    Cada tabla se guarda como un CSV separado dentro de la carpeta indicada."""
    carpeta = Path(carpeta_salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, df in tablas.items():
        ruta = carpeta / f"{nombre}.csv"
        df.to_csv(ruta, index=False, encoding="utf-8-sig")
        logger.info("CSV '%s' exportado con %d filas", ruta, len(df))


def exportar_a_excel_si_disponible(tablas, ruta_excel):
    """Si openpyxl/xlsxwriter estan instalados, exporta a Excel con una hoja
    por tabla. Si no, registra una advertencia y no hace nada."""
    for engine in ("openpyxl", "xlsxwriter"):
        try:
            __import__(engine)
        except ImportError:
            continue
        with pd.ExcelWriter(ruta_excel, engine=engine) as writer:
            for nombre_hoja, df in tablas.items():
                df.to_excel(writer, sheet_name=nombre_hoja, index=False)
                logger.info("Hoja '%s' exportada con %d filas", nombre_hoja, len(df))
        return
    logger.warning(
        "No se encontro openpyxl/xlsxwriter; se omite la exportacion a Excel."
    )


def main():
    """Punto de entrada: construye y exporta el modelo estrella."""
    logger.info("Cargando datos procesados...")
    df = _leer_datos_procesados()
    logger.info("Datos cargados: %d filas, %d columnas", len(df), df.shape[1])

    logger.info("Construyendo tablas del modelo estrella...")
    tablas = {
        "fact_lecturas":       construir_fact_lecturas(df),
        "dim_ciudad":          construir_dim_ciudad(),
        "dim_tiempo":          construir_dim_tiempo(df),
        "dim_categoria_aqi":   construir_dim_categoria_aqi(),
        "fact_predicciones":   construir_fact_predicciones(),
        "fact_resumenes":      construir_fact_resumenes(),
    }

    carpeta_salida = PROCESSED_DIR / "modelo_estrella"
    ruta_excel = PROCESSED_DIR / "modelo_estrella_powerbi.xlsx"

    exportar_a_carpeta(tablas, carpeta_salida)
    exportar_a_excel_si_disponible(tablas, ruta_excel)

    print("\n=== Modelo estrella exportado ===")
    for nombre, df in tablas.items():
        print(f"  {nombre:20s}: {len(df):5d} filas, {df.shape[1]:2d} columnas")
    print(f"\nCarpeta CSVs:  {carpeta_salida}")
    print(f"Excel (si se pudo): {ruta_excel}")
    print("\nRelaciones sugeridas en Power BI:")
    print("  fact_lecturas[ciudad]         -> dim_ciudad[ciudad]")
    print("  fact_lecturas[fecha]          -> dim_tiempo[fecha]")
    print("  fact_lecturas[categoria_aqi]  -> dim_categoria_aqi[categoria_aqi]")
    print("  fact_predicciones[ciudad]     -> dim_ciudad[ciudad]")
    print("  fact_resumenes[fecha]         -> dim_tiempo[fecha]")


if __name__ == "__main__":
    main()
