"""
models/prediccion.py
====================
Predicción de PM2.5 para las próximas 24 horas. Usa Prophet si está
disponible; de lo contrario cae automáticamente a una regresión lineal de
scikit-learn, sin que el usuario tenga que cambiar nada.
"""

import logging
from datetime import timedelta

import numpy as np
import pandas as pd

from config import CSV_PROCESADO, PROCESSED_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Detección de Prophet con fallback automático.
try:
    from prophet import Prophet
    PROPHET_DISPONIBLE = True
    logger.info("Prophet disponible: se usará para la predicción.")
except ImportError:
    from sklearn.linear_model import LinearRegression
    PROPHET_DISPONIBLE = False
    logger.warning("Prophet no disponible: se usará LinearRegression (fallback).")


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
    if not CSV_PROCESADO.exists():
        logger.error("No existe %s. Ejecute primero el pipeline.", CSV_PROCESADO)
        return pd.DataFrame()

    df = pd.read_csv(CSV_PROCESADO)
    df = df[df["ciudad"] == ciudad].copy()
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp", "pm25"]).sort_values("timestamp")
    return df


def _predecir_prophet(df):
    """
    Genera la predicción de PM2.5 a 24h con Prophet.

    Parámetros
    ----------
    df : pandas.DataFrame
        Datos históricos de la ciudad (con 'timestamp' y 'pm25').

    Retorna
    -------
    pandas.DataFrame
        Columnas: hora, pm25_predicho, lower, upper.
    """
    entreno = pd.DataFrame({
        "ds": df["timestamp"].dt.tz_localize(None),
        "y": df["pm25"].astype(float),
    })

    modelo = Prophet(seasonality_mode="multiplicative",
                     daily_seasonality=True)
    modelo.fit(entreno)

    futuro = modelo.make_future_dataframe(periods=24, freq="H")
    pronostico = modelo.predict(futuro)
    futuro_24 = pronostico.tail(24)

    return pd.DataFrame({
        "hora": futuro_24["ds"].values,
        "pm25_predicho": futuro_24["yhat"].values,
        "lower": futuro_24["yhat_lower"].values,
        "upper": futuro_24["yhat_upper"].values,
    })


def _predecir_lineal(df):
    """
    Fallback: predicción de PM2.5 a 24h con regresión lineal usando
    hora_del_dia y dia_semana como features.

    Parámetros
    ----------
    df : pandas.DataFrame
        Datos históricos de la ciudad.

    Retorna
    -------
    pandas.DataFrame
        Columnas: hora, pm25_predicho, lower, upper.
    """
    from sklearn.linear_model import LinearRegression

    # Asegurar features temporales.
    if "hora_del_dia" not in df.columns:
        df["hora_del_dia"] = df["timestamp"].dt.hour
    if "dia_semana" not in df.columns:
        df["dia_semana"] = df["timestamp"].dt.dayofweek

    X = df[["hora_del_dia", "dia_semana"]].astype(float)
    y = df["pm25"].astype(float)

    modelo = LinearRegression()
    modelo.fit(X, y)

    # Margen de confianza aproximado a partir del error residual.
    residual = y - modelo.predict(X)
    margen = float(np.std(residual)) if len(residual) > 1 else 5.0

    # Generar las próximas 24 horas a partir de la última marca conocida.
    ultima = df["timestamp"].max()
    horas_futuras = [ultima + timedelta(hours=h) for h in range(1, 25)]
    X_fut = pd.DataFrame({
        "hora_del_dia": [t.hour for t in horas_futuras],
        "dia_semana": [t.dayofweek for t in horas_futuras],
    }).astype(float)

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
    Entrena el modelo de PM2.5 para una ciudad y predice las próximas 24h.

    Usa Prophet si está disponible; de lo contrario regresión lineal. Guarda
    el resultado en data/processed/predicciones_{ciudad}.csv.

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
    df = _cargar_ciudad(ciudad)
    if df.empty or len(df) < 2:
        logger.error("Datos insuficientes para predecir en %s.", ciudad)
        return pd.DataFrame(columns=["hora", "pm25_predicho", "lower", "upper"])

    try:
        if PROPHET_DISPONIBLE:
            resultado = _predecir_prophet(df)
        else:
            resultado = _predecir_lineal(df)
    except Exception as exc:  # noqa: BLE001 - fallback de seguridad
        logger.error("Prophet falló (%s); usando regresión lineal.", exc)
        resultado = _predecir_lineal(df)

    # Guardar predicción.
    ciudad_slug = ciudad.lower().replace(" ", "_")
    ruta = PROCESSED_DIR / f"predicciones_{ciudad_slug}.csv"
    try:
        resultado.to_csv(ruta, index=False)
        logger.info("Predicción guardada en %s", ruta)
    except OSError as exc:
        logger.error("No se pudo guardar la predicción: %s", exc)

    return resultado


if __name__ == "__main__":
    from config import CIUDADES
    primera = next(iter(CIUDADES))
    pred = entrenar_y_predecir(primera)
    print(f"\n=== Predicción 24h para {primera} ===")
    print(pred.to_string(index=False))
