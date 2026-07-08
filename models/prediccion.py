"""
models/prediccion.py
====================
Predicción de PM2.5 para las próximas 24 horas usando regresión lineal de
scikit-learn (hora_del_dia y dia_semana como features).
"""

import logging
from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from config import CSV_PROCESADO, PROCESSED_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _cargar_ciudad(ciudad):
    """
    Carga y filtra el dataset procesado para una ciudad concreta.

    Parámetros
    ----------
    ciudad : str
        Nombre de la ciudad a filtrar.

    Retorna
    -------
    pandas.DataFrame
        Filas de esa ciudad con timestamp como datetime, ordenadas en el
        tiempo. Vacío si no hay datos.
    """
    # Verificar que el archivo procesado exista.
    if not CSV_PROCESADO.exists():
        logger.error("No existe %s. Ejecute primero el pipeline.", CSV_PROCESADO)
        return pd.DataFrame()

    # Leer el CSV y filtrar por ciudad.
    df = pd.read_csv(CSV_PROCESADO)
    df = df[df["ciudad"] == ciudad].copy()
    if df.empty:
        return df
    # Convertir timestamp a datetime y eliminar filas con valores nulos.
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp", "pm25"]).sort_values("timestamp")
    return df


def _predecir_lineal(df):
    """
    Predicción de PM2.5 a 24h con regresión lineal usando hora_del_dia y
    dia_semana como features.

    Parámetros
    ----------
    df : pandas.DataFrame
        Datos históricos de la ciudad.

    Retorna
    -------
    pandas.DataFrame
        Columnas: hora, pm25_predicho, lower, upper.
    """
    # Asegurar features temporales.
    if "hora_del_dia" not in df.columns:
        df["hora_del_dia"] = df["timestamp"].dt.hour
    if "dia_semana" not in df.columns:
        df["dia_semana"] = df["timestamp"].dt.dayofweek

    # Definir variables predictoras y objetivo.
    X = df[["hora_del_dia", "dia_semana"]].astype(float)
    y = df["pm25"].astype(float)

    modelo = LinearRegression()
    modelo.fit(X, y)

    # Calcular margen de confianza basado en el error residual.
    residual = y - modelo.predict(X)
    margen = float(np.std(residual)) if len(residual) > 1 else 5.0

    # Generar marcas de tiempo para las próximas 24 horas.
    ultima = df["timestamp"].max()
    horas_futuras = [ultima + timedelta(hours=h) for h in range(1, 25)]
    X_fut = pd.DataFrame({
        "hora_del_dia": [t.hour for t in horas_futuras],
        "dia_semana": [t.dayofweek for t in horas_futuras],
    }).astype(float)

    # Realizar predicción y limitar valores negativos a 0.
    pred = modelo.predict(X_fut)
    pred = np.clip(pred, 0, None)  # PM2.5 no puede ser negativo

    return pd.DataFrame({
        "hora": horas_futuras,
        "pm25_predicho": pred,
        "lower": np.clip(pred - margen, 0, None),
        "upper": pred + margen,
    })


def entrenar_y_predecir(ciudad):
    """
    Entrena el modelo de regresión lineal de PM2.5 para una ciudad y predice
    las próximas 24h. Guarda el resultado en
    data/processed/predicciones_{ciudad}.csv.

    Parámetros
    ----------
    ciudad : str
        Ciudad a predecir.

    Retorna
    -------
    pandas.DataFrame
        Predicción con columnas hora, pm25_predicho, lower, upper. Vacío si
        no hay datos suficientes.
    """
    # Cargar datos históricos de la ciudad.
    df = _cargar_ciudad(ciudad)
    if df.empty or len(df) < 2:
        logger.error("Datos insuficientes para predecir en %s.", ciudad)
        return pd.DataFrame(columns=["hora", "pm25_predicho", "lower", "upper"])

    resultado = _predecir_lineal(df)

    # Guardar la predicción en un archivo CSV.
    ciudad_slug = ciudad.lower().replace(" ", "_")
    ruta = PROCESSED_DIR / f"predicciones_{ciudad_slug}.csv"
    try:
        resultado.to_csv(ruta, index=False)
        logger.info("Predicción guardada en %s", ruta)
    except OSError as exc:
        logger.error("No se pudo guardar la predicción: %s", exc)

    return resultado


if __name__ == "__main__":
    # Ejemplo de uso: predecir para la primera ciudad de la lista.
    from config import CIUDADES
    primera = next(iter(CIUDADES))
    pred = entrenar_y_predecir(primera)
    print(f"\n=== Predicción 24h para {primera} ===")
    print(pred.to_string(index=False))
