"""
dashboard/app.py
================
Dashboard interactivo en Streamlit para el Monitor de Calidad del Aire en
America Latina. Incluye KPIs, mapa Folium, resumen LLM, graficas en pestanas
y una tabla de alertas.

Ejecutar con: streamlit run dashboard/app.py
"""

import sys
from datetime import date
from html import escape
from pathlib import Path

# Permitir importar los paquetes del proyecto (config, pipeline, models, llm)
# al ejecutar este archivo directamente con streamlit desde la carpeta dashboard/.
sys.path.append(str(Path(__file__).resolve().parent.parent))

import folium
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from config import CIUDADES, CSV_PROCESADO, get_categoria_aqi, PAIS_POR_CIUDAD
from llm.resumenes import generar_resumen_diario
from models.clasificador import get_feature_importance
from models.prediccion import entrenar_y_predecir
from pipeline.actualizar import ejecutar_pipeline

# Mapeo entre el nombre mostrado en el selector y la columna real del CSV.
CONTAMINANTES = {"PM2.5": "pm25", "PM10": "pm10", "CO": "co", "O3": "o3"}


@st.cache_data(ttl=300)
def cargar_datos():
    """Carga el dataset procesado desde CSV y normaliza tipos numericos."""
    # Si todavia no se ha corrido el pipeline, no hay archivo que leer.
    if not CSV_PROCESADO.exists():
        return pd.DataFrame()

    df = pd.read_csv(CSV_PROCESADO)

    # Convertir la columna de fecha/hora a datetime real (con zona UTC)
    # para poder filtrar y graficar correctamente.
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

    # Asegurar que las columnas de contaminantes sean numericas;
    # cualquier valor invalido se convierte en NaN en vez de romper el dashboard.
    columnas_numericas = ["aqi", "pm25", "pm10", "co", "o3"]
    for col in columnas_numericas:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def ultimas_lecturas(df):
    """Devuelve la lectura mas reciente por ciudad."""
    # Se usa para KPIs, mapa y alertas: siempre se muestra el dato mas actual
    # de cada ciudad, no el historico completo.
    if df.empty:
        return df
    return df.sort_values("timestamp").groupby("ciudad", as_index=False).tail(1)


def _inyectar_estilos():
    # CSS personalizado para que las metricas y el sidebar no corten texto
    # cuando los nombres de ciudades/categorias son largos
    # (ej. "Ciudad de Guatemala", "Dañino para grupos sensibles").
    st.markdown(
        """
        <style>
        /* Forzar wrap en todas las métricas */
        div[data-testid="stMetricValue"] {
            white-space: normal !important;
            word-break: break-word !important;
            overflow-wrap: break-word !important;
            text-overflow: clip !important;
        }
        div[data-testid="stMetricLabel"] {
            white-space: normal !important;
        }
        /* Sidebar multiselect (opcional, para nombres largos en filtros) */
        [data-testid="stSidebar"] [data-baseweb="tag"] {
            height: auto;
            max-width: 100%;
            white-space: normal;
            word-break: break-word;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"] span {
            overflow: visible;
            text-overflow: clip;
            white-space: normal;
            word-break: break-word;
        }
        [data-testid="stSidebar"] div[role="option"] {
            height: auto;
            min-height: 36px;
            white-space: normal;
            word-break: break-word;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _popup_ciudad(ciudad, txt_aqi, pm25_txt, txt_cat):
    # Construye el HTML que se muestra al hacer click en el marcador del mapa.
    # escape() evita que nombres con caracteres especiales rompan el HTML.
    ciudad_html = escape(str(ciudad))
    categoria_html = escape(str(txt_cat))
    return (
        "<div style='font-size:14px; padding:8px; min-width:180px; "
        "max-width:260px; line-height:1.7; font-family:Arial, sans-serif; "
        "color:#111827;'>"
        f"<strong style='font-size:16px'>{ciudad_html}</strong>"
        "<hr style='margin:6px 0'>"
        f"AQI: <strong>{escape(str(txt_aqi))}</strong><br>"
        f"PM2.5: <strong>{escape(str(pm25_txt))}</strong><br>"
        f"Categoria: <strong>{categoria_html}</strong>"
        "</div>"
    )


def _tooltip_ciudad(ciudad, txt_aqi, txt_cat):
    # Construye el tooltip (texto flotante) que aparece al pasar el mouse
    # sobre un marcador, sin necesidad de hacer click.
    ciudad_html = escape(str(ciudad))
    categoria_html = escape(str(txt_cat))
    return folium.Tooltip(
        (
            f"<div><strong>{ciudad_html}</strong><br>"
            f"AQI {escape(str(txt_aqi))} - {categoria_html}</div>"
        ),
        sticky=True,
        style=(
            "background-color:#ffffff; color:#111827; "
            "font-family:Arial, sans-serif; font-size:14px; "
            "font-weight:400; line-height:1.35; "
            "border:1px solid #9ca3af; border-radius:6px; "
            "box-shadow:0 4px 10px rgba(17,24,39,.18); "
            "padding:8px 10px; max-width:260px; white-space:normal;"
        ),
    )


# Configuracion general de la pagina: titulo de la pestana, ancho completo
# e icono. Debe ser el primer comando de Streamlit en ejecutarse.
st.set_page_config(
    page_title="Monitor Ambiental",
    layout="wide",
    page_icon=":earth_americas:",
)
_inyectar_estilos()

st.title("Monitor de Calidad del Aire y Datos Ambientales de America Latina")
st.caption("Universidad Tecnologica de Panama - Gestion de la Informacion - Parcial #2")

# Carga inicial de datos (cacheada por 5 minutos, ver @st.cache_data arriba).
df = cargar_datos()

# Sidebar: filtros que controlan que datos se muestran
st.sidebar.header("Filtros")

ciudades_disponibles = list(CIUDADES.keys())

# Lista de paises unicos derivada del diccionario PAIS_POR_CIUDAD.
# Ciudades sin pais asignado caen en "Otros".
paises_disponibles = sorted(set(PAIS_POR_CIUDAD.get(c, "Otros") for c in ciudades_disponibles))

# Filtro principal por pais (con buscador y checkboxes integrados de Streamlit).
# Por defecto todos los paises estan seleccionados.
paises_sel = st.sidebar.multiselect(
    "Países",
    paises_disponibles,
    default=paises_disponibles,
    help="Escribe para buscar un país. Haz clic para agregar o quitar de la selección.",
)

# A partir de los paises elegidos, se calcula que ciudades quedan disponibles.
ciudades_filtradas_por_pais = [
    c for c in ciudades_disponibles
    if PAIS_POR_CIUDAD.get(c, "Otros") in paises_sel
]

# Filtro secundario (opcional) para afinar y quitar ciudades especificas
# dentro de los paises ya seleccionados. Va dentro de un expander para
# no saturar la barra lateral.
with st.sidebar.expander("Afinar ciudades", expanded=False):
    ciudades_sel = st.multiselect(
        "Ciudades",
        ciudades_filtradas_por_pais,
        default=ciudades_filtradas_por_pais,
        help="Escribe para buscar una ciudad específica.",
    )

# Calcular el rango de fechas disponible a partir de los datos cargados;
# si no hay datos, se usa la fecha de hoy como valor por defecto.
if not df.empty and df["timestamp"].notna().any():
    fecha_min = df["timestamp"].min().date()
    fecha_max = df["timestamp"].max().date()
else:
    fecha_min = fecha_max = date.today()

rango_fechas = st.sidebar.date_input("Rango de fechas", value=(fecha_min, fecha_max))

# Selector del contaminante que se graficara en la pestana de serie temporal.
contaminante_label = st.sidebar.selectbox(
    "Contaminante a graficar",
    list(CONTAMINANTES.keys()),
)
contaminante_col = CONTAMINANTES[contaminante_label]

# Boton para correr el pipeline completo (ingesta + preprocesamiento)
# manualmente desde el dashboard y refrescar los datos en pantalla.
if st.sidebar.button("Actualizar datos"):
    with st.spinner("Ejecutando pipeline completo..."):
        ejecutar_pipeline()
    st.cache_data.clear()
    st.success("Datos actualizados. Recargando...")
    st.rerun()


# Aplicar filtros seleccionados al DataFrame principal

# Si nunca se corrio el pipeline, mostrar instrucciones y detener la app aqui.
if df.empty:
    st.warning(
        "No hay datos procesados todavia. Ejecuta el pipeline con "
        "`python -m pipeline.actualizar --now` o usa el boton "
        "Actualizar datos en la barra lateral."
    )
    st.stop()

# Filtrar por las ciudades seleccionadas en el sidebar.
df_filtrado = df[df["ciudad"].isin(ciudades_sel)].copy()

# Filtrar por el rango de fechas seleccionado (si el usuario elegio dos fechas).
if isinstance(rango_fechas, (list, tuple)) and len(rango_fechas) == 2:
    inicio, fin = rango_fechas
    fechas = df_filtrado["timestamp"].dt.date
    df_filtrado = df_filtrado[(fechas >= inicio) & (fechas <= fin)]

# Si los filtros dejan el dataset vacio, avisar y detener la app aqui.
if df_filtrado.empty:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()

# Lectura mas reciente por ciudad, usada en KPIs, mapa y alertas.
ultimas = ultimas_lecturas(df_filtrado)


# KPIs: tarjetas resumen en la parte superior del dashboard

col1, col2, col3, col4 = st.columns([0.8, 2, 1, 2])

# Promedios generales considerando solo las ciudades/fechas filtradas.
aqi_prom = ultimas["aqi"].mean(skipna=True)
pm25_prom = ultimas["pm25"].mean(skipna=True)

# Ciudad con el peor AQI actual (la mas contaminada).
if ultimas["aqi"].notna().any():
    fila_max = ultimas.loc[ultimas["aqi"].idxmax()]
    ciudad_max = fila_max["ciudad"]
    aqi_max = fila_max["aqi"]
else:
    ciudad_max, aqi_max = "N/D", 0

# Categoria AQI general (Bueno/Moderado/etc.) basada en el promedio.
if pd.notna(aqi_prom):
    categoria_general = get_categoria_aqi(int(round(aqi_prom)))
else:
    categoria_general = {"etiqueta": "Sin datos", "color": "#7f8c8d"}

col1.metric("AQI promedio actual", f"{aqi_prom:.0f}" if pd.notna(aqi_prom) else "N/D")
col2.metric(
    "Ciudad mas contaminada",
    ciudad_max,
    f"AQI {aqi_max:.0f}" if pd.notna(aqi_max) and aqi_max > 0 else "N/D",
)
col3.metric("PM2.5 promedio", f"{pm25_prom:.1f}" if pd.notna(pm25_prom) else "N/D")
col4.metric("Categoria general", categoria_general.get("etiqueta", "Sin datos"))

# Barra de color debajo de la metrica que refuerza visualmente la categoria
# (verde = bueno, rojo = dañino, etc.) usando el color definido en config.py.
col4.markdown(
    f"<div style='height:8px;background:{categoria_general.get('color', '#7f8c8d')};"
    "border-radius:4px'></div>",
    unsafe_allow_html=True,
)

st.divider()


# Mapa interactivo + resumen generado por IA

col_mapa, col_resumen = st.columns([3, 2])

with col_mapa:
    st.subheader("Mapa de calidad del aire en America Latina")

    # Mapa base centrado en America Latina con zoom inicial bajo
    # para ver todo el continente.
    mapa = folium.Map(
        location=[-20, -75],
        zoom_start=2,
        tiles="CartoDB positron",
        max_bounds=True,
        min_zoom=2,
    )

    # Un marcador circular por cada ciudad con datos disponibles.
    for _, fila in ultimas.iterrows():
        info = CIUDADES.get(fila["ciudad"])
        # Si la ciudad no tiene coordenadas registradas en config.py, se omite.
        if info is None:
            continue

        aqi_val = fila["aqi"] if pd.notna(fila["aqi"]) else None
        pm25_txt = f"{fila['pm25']:.1f}" if pd.notna(fila["pm25"]) else "N/D"

        # Determinar color y tamaño del circulo segun el AQI:
        # mayor AQI -> circulo mas grande y color mas "alarmante".
        if aqi_val is not None:
            categoria = get_categoria_aqi(int(round(aqi_val)))
            color = categoria.get("color", "#9E9E9E")
            radio = max(8, min(40, float(aqi_val) / 5))
            txt_aqi = f"{aqi_val:.0f}"
            txt_cat = categoria.get("etiqueta", "Sin datos")
        else:
            # Ciudad sin lectura de AQI: marcador gris neutro.
            color = "#9E9E9E"
            radio = 8
            txt_aqi = "N/D"
            txt_cat = "Sin datos"

        # Dibujar el marcador con su popup (al hacer click) y tooltip (al pasar el mouse).
        folium.CircleMarker(
            location=[info["lat"], info["lon"]],
            radius=radio,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.65,
            popup=folium.Popup(
                _popup_ciudad(fila["ciudad"], txt_aqi, pm25_txt, txt_cat),
                max_width=280,
                min_width=180,
            ),
            tooltip=_tooltip_ciudad(fila["ciudad"], txt_aqi, txt_cat),
        ).add_to(mapa)

    # returned_objects=[] evita que Streamlit re-ejecute el script
    # cada vez que el usuario mueve o hace zoom en el mapa.
    st_folium(mapa, width=None, height=420, returned_objects=[])

with col_resumen:
    st.subheader("Resumen del dia")

    # El resumen se genera una sola vez por sesion y se guarda en
    # session_state para no llamar al LLM en cada recarga del dashboard.
    if "resumen" not in st.session_state:
        with st.spinner("Generando resumen..."):
            st.session_state["resumen"] = generar_resumen_diario(ultimas)
    st.info(st.session_state["resumen"])

    # Boton para forzar una nueva llamada al LLM y refrescar el resumen.
    if st.button("Regenerar resumen"):
        with st.spinner("Regenerando resumen..."):
            st.session_state["resumen"] = generar_resumen_diario(ultimas)
        st.rerun()

st.divider()


# Graficas en pestañas

tab1, tab2, tab3, tab4 = st.tabs(
    [
        f"Serie temporal {contaminante_label}",
        "Prediccion 24h",
        "Importancia de features",
        "Correlacion",
    ]
)

# --- Tab 1: evolucion del contaminante elegido a lo largo del tiempo ---
with tab1:
    if (
        contaminante_col in df_filtrado.columns
        and not df_filtrado[contaminante_col].isna().all()
    ):
        fig = px.line(
            df_filtrado.sort_values("timestamp"),
            x="timestamp",
            y=contaminante_col,
            color="ciudad",
            markers=True,
            labels={"timestamp": "Tiempo", contaminante_col: contaminante_label},
            title=f"Evolucion de {contaminante_label} por ciudad",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(
            f"No hay datos de {contaminante_label} disponibles para el rango de fechas."
        )

# --- Tab 2: prediccion de PM2.5 para las proximas 24 horas ---
with tab2:
    ciudad_pred = st.selectbox("Ciudad para predecir", ciudades_sel or ciudades_disponibles)

    # La prediccion se guarda en session_state para no recalcularla
    # automaticamente; solo se genera cuando el usuario presiona el boton.
    pred_state = st.session_state.get("prediccion_24h", {})

    if st.button("Generar prediccion", key="generar_prediccion_24h"):
        with st.spinner(f"Generando prediccion para {ciudad_pred}..."):
            pred_state = {
                "ciudad": ciudad_pred,
                "data": entrenar_y_predecir(ciudad_pred),
            }
            st.session_state["prediccion_24h"] = pred_state

    pred = pred_state.get("data")

    # Si el usuario cambio de ciudad pero no volvio a presionar el boton,
    # se le pide que genere la prediccion para la nueva ciudad.
    if pred_state.get("ciudad") != ciudad_pred:
        st.info("Selecciona una ciudad y presiona Generar prediccion.")
    elif pred is None or pred.empty:
        st.info("No hay datos suficientes para predecir esta ciudad.")
    else:
        # Grafica de linea con banda de confianza (area entre "lower" y "upper").
        fig_pred = go.Figure()

        # Linea superior del intervalo (invisible, solo define el borde del area).
        fig_pred.add_trace(
            go.Scatter(
                x=pred["hora"],
                y=pred["upper"],
                mode="lines",
                line=dict(width=0),
                showlegend=False,
                name="upper",
            )
        )
        # Linea inferior del intervalo; "fill=tonexty" rellena el area
        # entre esta linea y la anterior (upper), creando la banda de confianza.
        fig_pred.add_trace(
            go.Scatter(
                x=pred["hora"],
                y=pred["lower"],
                mode="lines",
                fill="tonexty",
                fillcolor="rgba(0,150,80,0.2)",
                line=dict(width=0),
                name="Intervalo de confianza",
            )
        )
        # Linea principal con el valor predicho de PM2.5.
        fig_pred.add_trace(
            go.Scatter(
                x=pred["hora"],
                y=pred["pm25_predicho"],
                mode="lines+markers",
                line=dict(color="#00964F", width=2),
                name="PM2.5 predicho",
            )
        )
        fig_pred.update_layout(
            title=f"Prediccion de PM2.5 - proximas 24h ({ciudad_pred})",
            xaxis_title="Hora",
            yaxis_title="PM2.5",
        )
        st.plotly_chart(fig_pred, use_container_width=True)

# --- Tab 3: que tan importante es cada feature para el clasificador ---
with tab3:
    importancias = get_feature_importance()
    if importancias is None or importancias.empty:
        st.info("El modelo clasificador aun no esta entrenado o no tiene datos suficientes.")
    else:
        fig_imp = px.bar(
            importancias.sort_values("importancia"),
            x="importancia",
            y="feature",
            orientation="h",
            title="Importancia de features del clasificador",
            labels={"importancia": "Importancia", "feature": "Feature"},
        )
        st.plotly_chart(fig_imp, use_container_width=True)

# --- Tab 4: correlacion entre variables numericas ---
with tab4:
    numericas = df_filtrado.select_dtypes(include="number")

    # Se excluyen columnas que son categoricas codificadas como numeros
    # (no aportan informacion util en una matriz de correlacion).
    numericas = numericas.drop(
        columns=[
            c
            for c in ["es_fin_de_semana", "mes", "riesgo_salud"]
            if c in numericas.columns
        ],
        errors="ignore",
    )
    if numericas.shape[1] >= 2:
        corr = numericas.corr()
        fig_corr = px.imshow(
            corr,
            text_auto=".2f",
            aspect="auto",
            color_continuous_scale="RdBu_r",
            zmin=-1,
            zmax=1,
            title="Matriz de correlacion entre variables numericas",
        )
        st.plotly_chart(fig_corr, use_container_width=True)
    else:
        st.info("No hay suficientes variables numericas para la correlacion.")

st.divider()


# Tabla de alertas: ciudades con AQI por encima de 100

st.subheader("Alertas (AQI > 100)")
alertas = ultimas[ultimas["aqi"] > 100].copy()

if alertas.empty:
    st.success("Ninguna ciudad supera un AQI de 100.")
else:
    columnas_mostrar = ["ciudad", "aqi", "pm25", "categoria_aqi", "riesgo_salud"]
    columnas_mostrar = [c for c in columnas_mostrar if c in alertas.columns]
    tabla = alertas[columnas_mostrar].sort_values("aqi", ascending=False)

    def _color_severidad(fila):
        # Colorea cada fila de la tabla segun el nivel de riesgo de salud:
        # rojo claro = alto riesgo, naranja = riesgo medio, amarillo = riesgo bajo.
        riesgo = fila.get("riesgo_salud", 0)
        if pd.isna(riesgo):
            estilo = "background-color: #f2f2f2; color: #1a1a1a"
        elif riesgo >= 2:
            estilo = "background-color: #ffcccc; color: #1a1a1a"
        elif riesgo == 1:
            estilo = "background-color: #ffe5b4; color: #1a1a1a"
        else:
            estilo = "background-color: #fff7cc; color: #1a1a1a"
        return [estilo] * len(fila)

    styler = tabla.style.apply(_color_severidad, axis=1)
    st.dataframe(styler, use_container_width=True)