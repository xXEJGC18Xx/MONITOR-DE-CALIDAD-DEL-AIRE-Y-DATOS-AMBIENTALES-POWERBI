"""
pipeline/ingesta_clima.py
=========================
Ingesta de datos climáticos desde Open-Meteo, API gratuita y sin clave.
Para cada ciudad obtiene la lectura horaria más cercana a la hora actual.

Referencia de arquitectura de pipeline periódico:
https://github.com/jimdowling/air_quality
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd
import requests

from config import CIUDADES, RAW_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 15  # segundos
MAX_WORKERS = 8


def _indice_hora_actual(horas_iso):
    """
    Encuentra el índice de la lista 'time' más cercano a la hora actual.

    Parámetros
    ----------
    horas_iso : list[str]
        Lista de marcas de tiempo ISO devueltas por Open-Meteo.

    Retorna
    -------
    int
        Índice de la lectura más reciente respecto a la hora actual.
    """
    if not horas_iso:
        return 0
    ahora = datetime.now()
    mejor_idx, mejor_dif = 0, None
    # Recorrer todas las marcas para hallar la más cercana a la hora actual.
    for idx, marca in enumerate(horas_iso):
        try:
            t = datetime.fromisoformat(marca)
        except ValueError:
            continue
        dif = abs((t - ahora).total_seconds())
        if mejor_dif is None or dif < mejor_dif:
            mejor_idx, mejor_dif = idx, dif
    return mejor_idx


def fetch_clima(ciudad, lat, lon):
    """
    Consulta el clima horario de una ciudad en Open-Meteo y devuelve la
    lectura más cercana a la hora actual.

    Parámetros
    ----------
    ciudad : str
        Nombre de la ciudad.
    lat : float
        Latitud.
    lon : float
        Longitud.

    Retorna
    -------
    dict
        Diccionario con ciudad, timestamp (ISO), temperatura,
        temperatura_aparente, humedad, viento_kmh, precipitacion_mm y
        codigo_clima. Campos ausentes quedan en None.
    """
    registro = {
        "ciudad": ciudad,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperatura": None,
        "temperatura_aparente": None,
        "humedad": None,
        "viento_kmh": None,
        "precipitacion_mm": None,
        "codigo_clima": None,
    }

    # Parámetros de la solicitud a Open-Meteo.
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": (
            "temperature_2m,relative_humidity_2m,wind_speed_10m,"
            "precipitation,weathercode,apparent_temperature"
        ),
        "timezone": "America/Panama",
        "forecast_days": 1,
    }

    try:
        respuesta = requests.get(OPEN_METEO_URL, params=params, timeout=TIMEOUT)
        respuesta.raise_for_status()
        payload = respuesta.json()
        horaria = payload.get("hourly", {})

        # Encontrar el índice de la hora más cercana a la actual.
        idx = _indice_hora_actual(horaria.get("time", []))

        # Función auxiliar para obtener el valor en el índice encontrado.
        def _val(clave):
            serie = horaria.get(clave)
            if isinstance(serie, list) and idx < len(serie):
                return serie[idx]
            return None

        # Asignar los valores al registro.
        registro["temperatura"] = _val("temperature_2m")
        registro["temperatura_aparente"] = _val("apparent_temperature")
        registro["humedad"] = _val("relative_humidity_2m")
        registro["viento_kmh"] = _val("wind_speed_10m")
        registro["precipitacion_mm"] = _val("precipitation")
        registro["codigo_clima"] = _val("weathercode")

        logger.info("Clima OK para %s (T=%s°C)", ciudad, registro["temperatura"])
    except requests.exceptions.RequestException as exc:
        logger.error("Error de red al consultar clima para %s: %s", ciudad, exc)
    except (ValueError, KeyError) as exc:
        logger.error("Error al procesar respuesta de clima para %s: %s", ciudad, exc)

    return registro


def fetch_clima_todas_ciudades():
    """
    Itera sobre todas las ciudades del config, consulta su clima, guarda el
    crudo en data/raw/ y consolida en un DataFrame.

    Retorna
    -------
    pandas.DataFrame
        DataFrame consolidado con una fila por ciudad.
    """
    registros_por_ciudad = {}
    # Consultar en paralelo usando ThreadPoolExecutor.
    workers = min(MAX_WORKERS, max(1, len(CIUDADES)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futuros = {
            executor.submit(fetch_clima, ciudad, info["lat"], info["lon"]): ciudad
            for ciudad, info in CIUDADES.items()
        }
        for futuro in as_completed(futuros):
            ciudad = futuros[futuro]
            try:
                registros_por_ciudad[ciudad] = futuro.result()
            except Exception as exc:  # noqa: BLE001 - resiliencia del pipeline
                logger.error("Fallo inesperado de clima con %s: %s", ciudad, exc)

    # Construir lista en el orden de las ciudades definidas.
    registros = [
        registros_por_ciudad[ciudad]
        for ciudad in CIUDADES
        if ciudad in registros_por_ciudad
    ]

    # Guardar el JSON crudo con marca de tiempo.
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    ruta_raw = RAW_DIR / f"clima_{marca}.json"
    try:
        with open(ruta_raw, "w", encoding="utf-8") as fh:
            json.dump(registros, fh, ensure_ascii=False, indent=2)
        logger.info("Crudo de clima guardado en %s", ruta_raw)
    except OSError as exc:
        logger.error("No se pudo guardar el crudo de clima: %s", exc)

    return pd.DataFrame(registros)


if __name__ == "__main__":
    # Prueba de la ingesta de clima.
    df = fetch_clima_todas_ciudades()
    print("\n=== DataFrame Clima consolidado ===")
    print(df.to_string(index=False))