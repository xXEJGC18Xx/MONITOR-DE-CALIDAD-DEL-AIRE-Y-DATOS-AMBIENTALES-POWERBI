"""
pipeline/actualizar.py
======================
Orquestador del pipeline completo. Ejecuta en secuencia la ingesta de WAQI,
la ingesta de clima, la fusión, el preprocesamiento, el guardado, la
predicción PM2.5 a 24h de todas las ciudades y el resumen diario del LLM.
Puede correr de forma programada (cada hora) o de inmediato con la bandera
--now.

Uso:
    python pipeline/actualizar.py --now    # ejecución inmediata (1 vez)
    python pipeline/actualizar.py          # modo programado (cada hora)
"""

import argparse
import logging
import time
from datetime import datetime

import pandas as pd
import schedule

from config import CIUDADES, CSV_PROCESADO, PROCESSED_DIR
from llm.resumenes import guardar_resumen_diario
from models.prediccion import entrenar_y_predecir
from pipeline.ingesta_clima import fetch_clima_todas_ciudades
from pipeline.ingesta_waqi import fetch_todas_ciudades
from pipeline.preprocesar import fusionar, guardar_procesado, preprocesar

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _paso(nombre, funcion, *args, **kwargs):
    """
    Ejecuta un paso del pipeline registrando inicio/fin y capturando errores.

    Parámetros
    ----------
    nombre : str
        Nombre legible del paso (para los logs).
    funcion : callable
        Función a ejecutar.
    *args, **kwargs :
        Argumentos que se pasan a la función.

    Retorna
    -------
    cualquier | None
        El valor devuelto por la función, o None si lanzó una excepción.
    """
    inicio = datetime.now()
    logger.info("▶ INICIO paso '%s' a las %s", nombre, inicio.isoformat())
    try:
        resultado = funcion(*args, **kwargs)
        fin = datetime.now()
        logger.info("✔ FIN paso '%s' (%.1fs)", nombre,
                    (fin - inicio).total_seconds())
        return resultado
    except Exception as exc:  # noqa: BLE001 - un paso no debe tumbar el resto
        logger.error("✖ ERROR en paso '%s': %s", nombre, exc)
        return None


def ejecutar_pipeline():
    """
    Ejecuta el pipeline ETL completo de extremo a extremo.

    Secuencia: WAQI -> clima -> fusión -> preprocesamiento -> guardado.
    El fallo de un paso queda registrado pero no interrumpe los demás.
    """
    logger.info("======== EJECUCIÓN DEL PIPELINE ========")

    # Paso 1: ingesta WAQI
    df_waqi = _paso("ingesta WAQI", fetch_todas_ciudades)
    # Paso 2: ingesta clima
    df_clima = _paso("ingesta clima", fetch_clima_todas_ciudades)

    # Si ambas ingestas fallaron, no se puede continuar.
    if df_waqi is None and df_clima is None:
        logger.error("Ambas ingestas fallaron; se aborta la fusión.")
        return

    # Paso 3: fusión de DataFrames
    fusion = _paso("fusión", fusionar,
                   df_waqi if df_waqi is not None else _df_vacio(),
                   df_clima if df_clima is not None else _df_vacio())
    # Paso 4: preprocesamiento
    procesado = _paso("preprocesamiento", preprocesar, fusion)
    # Paso 5: guardado si el preprocesamiento fue exitoso
    if procesado is not None:
        _paso("guardado", guardar_procesado, procesado)

    # Paso 6: predicción PM2.5 24h para todas las ciudades (alimenta fact_predicciones)
    if CSV_PROCESADO.exists():
        _paso("predicción PM2.5 24h (todas las ciudades)", _predecir_todas_ciudades)

    # Paso 7: generar resumen diario con LLM y persistirlo para Power BI
    if CSV_PROCESADO.exists():
        _paso("resumen diario LLM", _generar_y_guardar_resumen)

    logger.info("======== FIN DE LA EJECUCIÓN ========")


def _predecir_todas_ciudades():
    """
    Genera la predicción PM2.5 a 24h para cada ciudad configurada.

    Guarda un CSV por ciudad (data/processed/predicciones_{ciudad}.csv) para
    que exportar_powerbi.py pueda consolidarlos en fact_predicciones. Si una
    ciudad no tiene datos suficientes o falla, se registra el error y se
    continúa con las demás.
    """
    for ciudad in CIUDADES:
        try:
            entrenar_y_predecir(ciudad)
        except Exception as exc:  # noqa: BLE001 - una ciudad no debe tumbar las demás
            logger.error("Falló la predicción de %s: %s", ciudad, exc)


def _generar_y_guardar_resumen():
    """Carga el CSV procesado, toma las ultimas lecturas por ciudad y guarda
    el resumen diario generado por el LLM en data/processed/resumenes_diarios.csv."""
    datos = pd.read_csv(CSV_PROCESADO)
    ultimas = (
        datos.sort_values("timestamp")
        .groupby("ciudad", as_index=False)
        .tail(1)
    )
    guardar_resumen_diario(ultimas, PROCESSED_DIR)


def _df_vacio():
    """Devuelve un DataFrame vacío para usar como respaldo en la fusión."""
    import pandas as pd
    return pd.DataFrame()


def main():
    """Punto de entrada: parsea argumentos y elige modo de ejecución."""
    parser = argparse.ArgumentParser(
        description="Orquestador del pipeline ambiental de America Latina."
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Ejecuta el pipeline una sola vez de inmediato y termina.",
    )
    args = parser.parse_args()

    if args.now:
        # Modo único: ejecutar una vez y salir.
        logger.info("Modo --now: ejecución inmediata única.")
        ejecutar_pipeline()
        return

    # Modo programado: ejecutar ahora y luego cada hora.
    logger.info("Modo programado: el pipeline correrá cada hora.")
    ejecutar_pipeline()  # primera corrida inmediata
    schedule.every(1).hours.do(ejecutar_pipeline)
    # Bucle infinito para mantener el scheduler.
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()