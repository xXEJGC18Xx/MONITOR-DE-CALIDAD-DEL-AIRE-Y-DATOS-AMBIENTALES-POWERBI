"""
llm/resumenes.py
================
Generación de resúmenes diarios y alertas en lenguaje natural usando Groq
(Llama 3.1, gratuito). Todas las llamadas son tolerantes a fallos: si la API
no responde se devuelve un texto de respaldo en lugar de lanzar excepción.

Referencia de integración LLM + datos ambientales:
https://github.com/Alphawarrior21/VayuAssist
"""

import logging

from config import GROQ_API_KEY, GROQ_MAX_TOKENS, GROQ_MODELO

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _get_client():
    """
    Crea el cliente de Groq de forma perezosa.

    Retorna
    -------
    groq.Groq | None
        Cliente listo para usar, o None si falta la clave o el paquete.
    """
    # Si la API key no está configurada o es la de reemplazo, no se puede crear el cliente.
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("REEMPLAZAR"):
        logger.warning("GROQ_API_KEY no configurada; se usará respaldo.")
        return None
    try:
        from groq import Groq
        return Groq(api_key=GROQ_API_KEY)
    except ImportError:
        logger.error("Paquete 'groq' no instalado.")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.error("No se pudo inicializar el cliente Groq: %s", exc)
        return None


def _metricas_resumen(df):
    """
    Calcula las métricas globales que alimentan el prompt del resumen diario.

    Parámetros
    ----------
    df : pandas.DataFrame
        Dataset procesado con al menos las columnas ciudad, aqi y pm25.

    Retorna
    -------
    dict
        ciudad_max_aqi, ciudad_min_aqi, promedio_pm25, ciudades_sobre_100.
    """
    # Eliminamos filas sin AQI para poder obtener máximos/mínimos.
    df_validas = df.dropna(subset=["aqi"])
    # Si no hay datos válidos, devolvemos valores por defecto.
    if df_validas.empty:
        return {
            "ciudad_max_aqi": "N/D",
            "ciudad_min_aqi": "N/D",
            "promedio_pm25": 0.0,
            "ciudades_sobre_100": 0,
        }
    # Índices de la ciudad con mayor y menor AQI.
    idx_max = df_validas["aqi"].idxmax()
    idx_min = df_validas["aqi"].idxmin()
    return {
        "ciudad_max_aqi": f"{df_validas.loc[idx_max, 'ciudad']} (AQI {df_validas.loc[idx_max, 'aqi']:.0f})",
        "ciudad_min_aqi": f"{df_validas.loc[idx_min, 'ciudad']} (AQI {df_validas.loc[idx_min, 'aqi']:.0f})",
        "promedio_pm25": float(df["pm25"].mean(skipna=True) or 0.0),
        "ciudades_sobre_100": int((df_validas["aqi"] > 100).sum()),
    }


def generar_resumen_diario(df):
    """
    Genera un resumen diario en español (máx. 150 palabras) sobre el estado
    del aire en America Latina, usando Groq.

    Parámetros
    ----------
    df : pandas.DataFrame
        Dataset procesado del día.

    Retorna
    -------
    str
        Texto del resumen, o un mensaje de respaldo si la llamada falla.
    """
    # Obtenemos métricas resumidas del DataFrame.
    m = _metricas_resumen(df)
    # Texto de respaldo en caso de que la API falle.
    respaldo = (
        f"Estado del aire en America Latina: la ciudad con peor calidad es "
        f"{m['ciudad_max_aqi']} y la mejor es {m['ciudad_min_aqi']}. "
        f"El PM2.5 promedio es {m['promedio_pm25']:.1f}. "
        f"{m['ciudades_sobre_100']} ciudad(es) superan un AQI de 100. "
        f"Se recomienda a la población sensible limitar la exposición al aire libre."
    )

    # Intentamos obtener el cliente Groq; si no está disponible, devolvemos respaldo.
    cliente = _get_client()
    if cliente is None:
        return respaldo

    # Construimos el prompt con las métricas obtenidas.
    prompt = (
        "Eres un experto en calidad del aire y medio ambiente en América Latina. "
        "Los siguientes datos corresponden al monitoreo del día actual en diversas "
        "ciudades de la región:\n"
        f"- Ciudad con AQI más alto: {m['ciudad_max_aqi']}\n"
        f"- Ciudad con AQI más bajo: {m['ciudad_min_aqi']}\n"
        f"- Promedio de PM2.5 entre todas las ciudades monitoreadas: {m['promedio_pm25']:.1f}\n"
        f"- Número de ciudades con AQI mayor a 100: {m['ciudades_sobre_100']}\n\n"
        "Redacta un resumen de MÁXIMO 150 palabras en español que incluya: "
        "el estado general de la calidad del aire en la región, la ciudad más afectada "
        "y posibles causas (tráfico, industria, clima), recomendaciones prácticas para "
        "la población y, si alguna ciudad supera un AQI de 100, una frase de alerta "
        "indicando qué grupos son más vulnerables (niños, adultos mayores, personas "
        "con enfermedades respiratorias). "
        "Responde SOLO con el resumen, sin introducción ni explicaciones adicionales."
    )

    try:
        # Llamada a la API de Groq.
        respuesta = cliente.chat.completions.create(
            model=GROQ_MODELO,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=GROQ_MAX_TOKENS,
        )
        return respuesta.choices[0].message.content.strip()
    except Exception as exc:  # noqa: BLE001 - nunca propagar al dashboard
        logger.error("Fallo al generar resumen con Groq: %s", exc)
        return respaldo


def generar_alerta(ciudad, aqi):
    """
    Genera un mensaje de alerta corto y directo para una ciudad y su AQI.

    Parámetros
    ----------
    ciudad : str
        Nombre de la ciudad.
    aqi : int | float
        Valor de AQI registrado.

    Retorna
    -------
    str
        Mensaje de alerta breve, o un respaldo si la llamada falla.
    """
    # Texto de respaldo genérico.
    respaldo = (
        f"Alerta en {ciudad}: AQI de {aqi:.0f}. "
        f"Se recomienda reducir las actividades al aire libre, especialmente "
        f"para grupos sensibles."
    )

    cliente = _get_client()
    if cliente is None:
        return respaldo

    # Prompt específico para generar una alerta breve.
    prompt = (
        f"Eres un experto ambiental en America Latina. La ciudad de {ciudad} registra "
        f"un AQI de {aqi:.0f}. Escribe una alerta breve (máximo 40 palabras) en "
        f"español, clara y directa, con una recomendación concreta para la "
        f"población. Responde SOLO con la alerta."
    )

    try:
        respuesta = cliente.chat.completions.create(
            model=GROQ_MODELO,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
        )
        return respuesta.choices[0].message.content.strip()
    except Exception as exc:  # noqa: BLE001
        logger.error("Fallo al generar alerta con Groq: %s", exc)
        return respaldo


if __name__ == "__main__":
    # Ejecución de prueba: carga los datos procesados y muestra un resumen.
    import pandas as pd
    from config import CSV_PROCESADO

    if CSV_PROCESADO.exists():
        datos = pd.read_csv(CSV_PROCESADO)
        print(generar_resumen_diario(datos))
    else:
        print("No hay datos procesados; ejecute primero el pipeline.")