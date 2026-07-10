"""
llm/consultas.py
=================
Permite hacer preguntas en lenguaje natural sobre el estado actual de la
calidad del aire y el clima, usando el LLM de Groq (mismo modelo que
llm/resumenes.py).

No hay acceso directo del LLM a los datos: se arma un resumen en texto con
la ultima lectura de cada ciudad y se le pasa como contexto junto con la
pregunta del usuario, pidiendole que responda solo con base en eso.
"""

import logging

import pandas as pd

from config import CSV_PROCESADO, GROQ_API_KEY, GROQ_MODELO

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _get_client():
    """Crea el cliente de Groq de forma perezosa (igual que en resumenes.py)."""
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("REEMPLAZAR"):
        logger.warning("GROQ_API_KEY no configurada; no se puede consultar el LLM.")
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


def _construir_contexto(df):
    """
    Arma un resumen en texto con la ultima lectura de cada ciudad, ordenado
    de peor a mejor AQI, para usarlo como contexto del LLM.

    Parametros
    ----------
    df : pandas.DataFrame
        Dataset procesado completo (data/processed/datos.csv).

    Retorna
    -------
    str
        Un bloque de texto con una linea por ciudad.
    """
    ultimas = (
        df.sort_values("timestamp")
        .groupby("ciudad", as_index=False)
        .tail(1)
        .sort_values("aqi", ascending=False)
    )

    lineas = []
    for _, fila in ultimas.iterrows():
        lineas.append(
            f"- {fila.get('ciudad', 'N/D')}: AQI={fila.get('aqi', 'N/D')}, "
            f"categoria={fila.get('categoria_aqi', 'N/D')}, "
            f"PM2.5={fila.get('pm25', 'N/D')}, PM10={fila.get('pm10', 'N/D')}, "
            f"temperatura={fila.get('temperatura', 'N/D')}C, "
            f"humedad={fila.get('humedad', 'N/D')}%, "
            f"viento={fila.get('viento_kmh', 'N/D')}km/h"
        )
    return "\n".join(lineas)


def responder_pregunta(pregunta, historial=None):
    """
    Responde una pregunta en lenguaje natural sobre los datos ambientales
    actuales, usando el LLM de Groq.

    Parametros
    ----------
    pregunta : str
        Pregunta del usuario, en espanol.
    historial : list[dict] | None
        Lista opcional de mensajes previos (formato {"role", "content"})
        para mantener contexto de una conversacion de varias preguntas
        seguidas. Se puede omitir para preguntas sueltas.

    Retorna
    -------
    str
        Respuesta del modelo, o un mensaje de respaldo si el LLM no esta
        disponible o falla la llamada.
    """
    if not CSV_PROCESADO.exists():
        return "No hay datos procesados todavia. Ejecute primero el pipeline."

    df = pd.read_csv(CSV_PROCESADO)
    if df.empty:
        return "El dataset esta vacio. Ejecute primero el pipeline."

    contexto = _construir_contexto(df)

    cliente = _get_client()
    if cliente is None:
        return (
            "No se pudo conectar con el LLM (revise GROQ_API_KEY en .env). "
            "Este es el resumen de datos disponible:\n\n" + contexto
        )

    sistema = (
        "Eres un asistente experto en calidad del aire y clima en America "
        "Latina. A continuacion tienes la ultima lectura disponible de cada "
        "ciudad monitoreada. Responde las preguntas del usuario SOLO con "
        "base en estos datos; si te preguntan algo que no se puede "
        "responder con ellos, dilo claramente en vez de inventar.\n\n"
        f"{contexto}\n\n"
        "Responde siempre en espanol, de forma breve y directa "
        "(maximo 100 palabras)."
    )

    mensajes = [{"role": "system", "content": sistema}]
    if historial:
        mensajes.extend(historial)
    mensajes.append({"role": "user", "content": pregunta})

    try:
        respuesta = cliente.chat.completions.create(
            model=GROQ_MODELO,
            messages=mensajes,
            max_tokens=300,
        )
        return respuesta.choices[0].message.content.strip()
    except Exception as exc:  # noqa: BLE001 - nunca propagar al menu
        logger.error("Fallo al responder pregunta con Groq: %s", exc)
        return "Hubo un error consultando al LLM. Intenta de nuevo."


if __name__ == "__main__":
    # Modo de prueba rapida: una sola pregunta pasada como texto fijo.
    # Para la experiencia conversacional completa, usa python menu.py.
    pregunta_prueba = "Cual es la ciudad con peor calidad del aire ahora mismo?"
    print(f"Pregunta: {pregunta_prueba}\n")
    print(responder_pregunta(pregunta_prueba))
