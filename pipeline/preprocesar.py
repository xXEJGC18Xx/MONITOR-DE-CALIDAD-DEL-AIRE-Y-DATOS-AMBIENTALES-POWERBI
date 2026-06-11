"""
pipeline/preprocesar.py
=======================
Limpieza, fusión y feature engineering de los datos crudos de WAQI y clima.
Genera el dataset analítico final y lo persiste en CSV y SQLite.
"""

import glob
import logging
import sqlite3

import pandas as pd

from config import (
    CSV_PROCESADO,
    DB_PATH,
    RAW_DIR,
    get_categoria_aqi,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def cargar_ultimos_archivos():
    """
    Busca los archivos crudos más recientes de WAQI y clima en data/raw/.

    Ordena por nombre de forma descendente (el nombre incluye la marca de
    tiempo, así que el primero es el más nuevo) y carga ambos en DataFrames.

    Retorna
    -------
    tuple[pandas.DataFrame, pandas.DataFrame]
        (df_waqi, df_clima). Cualquiera puede venir vacío si no hay archivos.
    """
    waqi_files = sorted(glob.glob(str(RAW_DIR / "waqi_*.json")), reverse=True)
    clima_files = sorted(glob.glob(str(RAW_DIR / "clima_*.json")), reverse=True)

    df_waqi = pd.read_json(waqi_files[0]) if waqi_files else pd.DataFrame()
    df_clima = pd.read_json(clima_files[0]) if clima_files else pd.DataFrame()

    logger.info("Cargados %d registros WAQI y %d registros de clima",
                len(df_waqi), len(df_clima))
    return df_waqi, df_clima


def fusionar(df_waqi, df_clima):
    """
    Fusiona los DataFrames de WAQI y clima por la columna 'ciudad',
    evitando duplicar columnas presentes en ambas fuentes.

    Cuando una columna existe en ambos lados (ej. temperatura, humedad,
    timestamp) se conserva la versión de WAQI y se descarta la de clima.

    Parámetros
    ----------
    df_waqi : pandas.DataFrame
        Datos de calidad del aire.
    df_clima : pandas.DataFrame
        Datos climáticos.

    Retorna
    -------
    pandas.DataFrame
        DataFrame fusionado por ciudad.
    """
    if df_waqi.empty:
        return df_clima.copy()
    if df_clima.empty:
        return df_waqi.copy()

    # Columnas duplicadas (excepto la llave 'ciudad') se quitan del clima.
    columnas_comunes = (set(df_waqi.columns) & set(df_clima.columns)) - {"ciudad"}
    df_clima_reducido = df_clima.drop(columns=list(columnas_comunes), errors="ignore")

    fusion = pd.merge(df_waqi, df_clima_reducido, on="ciudad", how="outer")
    logger.info("Fusión completada: %d filas, %d columnas",
                len(fusion), fusion.shape[1])
    return fusion


def preprocesar(df):
    """
    Limpia el DataFrame fusionado y genera features derivados.

    Pasos:
      1. Convierte 'timestamp' a datetime con zona horaria UTC.
      2. Elimina filas con más del 50% de columnas nulas.
      3. Interpola valores numéricos faltantes (lineal, ambas direcciones).
      4. Genera: hora_del_dia, dia_semana (0-6), es_fin_de_semana (0/1),
         mes, categoria_aqi (texto), color_aqi (hex) y riesgo_salud (0/1/2).

    Parámetros
    ----------
    df : pandas.DataFrame
        DataFrame fusionado de WAQI + clima.

    Retorna
    -------
    pandas.DataFrame
        DataFrame limpio y enriquecido.
    """
    if df.empty:
        logger.warning("DataFrame vacío recibido en preprocesar().")
        return df

    df = df.copy()

    if "timestamp" not in df.columns:
        logger.warning("Columna timestamp ausente; se usará NaT.")
        df["timestamp"] = pd.NaT
    if "aqi" not in df.columns:
        logger.warning("Columna aqi ausente; se marcará como sin datos.")
        df["aqi"] = pd.NA

    # 1) timestamp -> datetime UTC
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

    # 2) eliminar filas con > 50% de nulos
    umbral_validos = int(df.shape[1] * 0.5)  # mínimo de valores no nulos
    df = df.dropna(thresh=umbral_validos).reset_index(drop=True)
    if df.empty:
        logger.warning("DataFrame vacío después de eliminar filas con demasiados nulos.")
        return df

    # 3) interpolación lineal de columnas numéricas
    columnas_num = df.select_dtypes(include="number").columns
    if len(columnas_num) > 0:
        df[columnas_num] = df[columnas_num].interpolate(
            method="linear", limit_direction="both"
        )

    # 4) feature engineering temporal
    df["hora_del_dia"] = df["timestamp"].dt.hour
    df["dia_semana"] = df["timestamp"].dt.dayofweek          # 0=lunes ... 6=domingo
    df["es_fin_de_semana"] = (df["dia_semana"] >= 5).astype(int)
    df["mes"] = df["timestamp"].dt.month

    # 4b) features derivados del AQI
    categorias = df["aqi"].apply(get_categoria_aqi)
    df["categoria_aqi"] = categorias.apply(lambda c: c["etiqueta"])
    df["color_aqi"] = categorias.apply(lambda c: c["color"])
    df["riesgo_salud"] = categorias.apply(lambda c: c["riesgo"])

    logger.info("Preprocesamiento completado: %d filas finales", len(df))
    return df


def guardar_procesado(df):
    """
    Persiste el DataFrame procesado en CSV (append + sin duplicados) y en
    una base SQLite (tabla 'lecturas', append).

    La deduplicación del CSV se hace por la combinación (ciudad, timestamp).

    Parámetros
    ----------
    df : pandas.DataFrame
        DataFrame procesado a guardar.
    """
    if df.empty:
        logger.warning("Nada que guardar: DataFrame vacío.")
        return

    # --- CSV con append + dedupe ---
    try:
        if CSV_PROCESADO.exists():
            previo = pd.read_csv(CSV_PROCESADO)
            combinado = pd.concat([previo, df], ignore_index=True)
        else:
            combinado = df.copy()

        combinado = combinado.drop_duplicates(
            subset=["ciudad", "timestamp"], keep="last"
        ).reset_index(drop=True)
        combinado.to_csv(CSV_PROCESADO, index=False)
        logger.info("CSV actualizado: %s (%d filas)", CSV_PROCESADO, len(combinado))
    except OSError as exc:
        logger.error("No se pudo escribir el CSV: %s", exc)

    # --- SQLite (tabla 'lecturas', append) ---
    try:
        conexion = sqlite3.connect(DB_PATH)
        df.to_sql("lecturas", conexion, if_exists="append", index=False)
        conexion.close()
        logger.info("Insertadas %d filas en SQLite (%s)", len(df), DB_PATH)
    except (sqlite3.Error, ValueError) as exc:
        logger.error("No se pudo escribir en SQLite: %s", exc)


if __name__ == "__main__":
    df_waqi, df_clima = cargar_ultimos_archivos()
    fusion = fusionar(df_waqi, df_clima)
    procesado = preprocesar(fusion)
    guardar_procesado(procesado)
    print("\n=== DataFrame procesado ===")
    print(procesado.to_string(index=False))
