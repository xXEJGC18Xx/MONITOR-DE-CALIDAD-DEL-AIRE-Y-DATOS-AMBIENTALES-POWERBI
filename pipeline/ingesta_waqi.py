"""
pipeline/ingesta_waqi.py
========================
Ingesta de datos de calidad del aire desde la API pública WAQI
(World Air Quality Index). Para cada ciudad consulta el endpoint
/feed/{waqi_id}/ y normaliza la respuesta en un diccionario plano.

Referencia de organización: https://github.com/oajetunm/air-quality-dashboard
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd
import requests

from config import CIUDADES, RAW_DIR, WAQI_TOKEN

# Configuración de logging del módulo.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

WAQI_BASE_URL = "https://api.waqi.info/feed"
TIMEOUT = 15  # segundos
MAX_WORKERS = 8


def _extraer(iaqi, clave):
    """
    Extrae de forma segura un contaminante del bloque 'iaqi' de WAQI.

    Parámetros
    ----------
    iaqi : dict
        Bloque "iaqi" de la respuesta de WAQI.
    clave : str
        Nombre del contaminante (ej. "pm25", "co").

    Retorna
    -------
    float | None
        Valor numérico o None si no está presente.
    """
    try:
        return iaqi.get(clave, {}).get("v")
    except AttributeError:
        return None


def fetch_waqi(ciudad):
    """
    Consulta la calidad del aire de una ciudad en la API WAQI.

    Parámetros
    ----------
    ciudad : str
        Nombre de la ciudad tal como aparece en config.CIUDADES.

    Retorna
    -------
    dict | None
        Diccionario normalizado con ciudad, timestamp (ISO), aqi, pm25,
        pm10, co, o3, no2, so2, temperatura y humedad. Los campos ausentes
        quedan en None. Retorna None si la ciudad no existe en el config.
    """
    info = CIUDADES.get(ciudad)
    if info is None:
        logger.error("Ciudad desconocida: %s", ciudad)
        return None

    url = f"{WAQI_BASE_URL}/{info['waqi_id']}/?token={WAQI_TOKEN}"
    registro = {
        "ciudad": ciudad,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "aqi": None,
        "pm25": None,
        "pm10": None,
        "co": None,
        "o3": None,
        "no2": None,
        "so2": None,
        "temperatura": None,
        "humedad": None,
    }

    try:
        respuesta = requests.get(url, timeout=TIMEOUT)
        respuesta.raise_for_status()
        payload = respuesta.json()

        if payload.get("status") != "ok":
            logger.warning("WAQI devolvió estado '%s' para %s",
                           payload.get("status"), ciudad)
            return registro

        data = payload.get("data", {})
        iaqi = data.get("iaqi", {})

        # El AQI principal viene como número directo.
        aqi_valor = data.get("aqi")
        registro["aqi"] = aqi_valor if isinstance(aqi_valor, (int, float)) else None
        registro["pm25"] = _extraer(iaqi, "pm25")
        registro["pm10"] = _extraer(iaqi, "pm10")
        registro["co"] = _extraer(iaqi, "co")
        registro["o3"] = _extraer(iaqi, "o3")
        registro["no2"] = _extraer(iaqi, "no2")
        registro["so2"] = _extraer(iaqi, "so2")
        registro["temperatura"] = _extraer(iaqi, "t")
        registro["humedad"] = _extraer(iaqi, "h")

        logger.info("WAQI OK para %s (AQI=%s)", ciudad, registro["aqi"])
    except requests.exceptions.RequestException as exc:
        logger.error("Error de red al consultar WAQI para %s: %s", ciudad, exc)
    except (ValueError, KeyError) as exc:
        logger.error("Error al procesar respuesta WAQI para %s: %s", ciudad, exc)

    return registro


def fetch_todas_ciudades():
    """
    Itera sobre todas las ciudades del config, consulta WAQI para cada una,
    guarda el resultado crudo como JSON en data/raw/ y consolida en un
    DataFrame de pandas.

    Un error en una ciudad se registra pero no detiene el procesamiento de
    las demás.

    Retorna
    -------
    pandas.DataFrame
        DataFrame consolidado con una fila por ciudad.
    """
    registros_por_ciudad = {}
    workers = min(MAX_WORKERS, max(1, len(CIUDADES)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futuros = {executor.submit(fetch_waqi, ciudad): ciudad for ciudad in CIUDADES}
        for futuro in as_completed(futuros):
            ciudad = futuros[futuro]
            try:
                resultado = futuro.result()
                if resultado is not None:
                    registros_por_ciudad[ciudad] = resultado
            except Exception as exc:  # noqa: BLE001 - resiliencia del pipeline
                logger.error("Fallo inesperado con %s: %s", ciudad, exc)

    registros = [
        registros_por_ciudad[ciudad]
        for ciudad in CIUDADES
        if ciudad in registros_por_ciudad
    ]

    # Guardar el crudo consolidado con marca de tiempo en el nombre.
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    ruta_raw = RAW_DIR / f"waqi_{marca}.json"
    try:
        with open(ruta_raw, "w", encoding="utf-8") as fh:
            json.dump(registros, fh, ensure_ascii=False, indent=2)
        logger.info("Crudo WAQI guardado en %s", ruta_raw)
    except OSError as exc:
        logger.error("No se pudo guardar el crudo WAQI: %s", exc)

    return pd.DataFrame(registros)


if __name__ == "__main__":
    df = fetch_todas_ciudades()
    print("\n=== DataFrame WAQI consolidado ===")
    print(df.to_string(index=False))
