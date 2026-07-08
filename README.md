# Monitor de Calidad del Aire y Datos Ambientales de América Latina

Sistema integral de monitoreo ambiental que recopila, procesa y analiza la calidad del aire y las condiciones climáticas de ciudades clave de América Latina. El proyecto integra un pipeline de datos automatizado (con ingestas paralelas a WAQI y Open-Meteo usando `ThreadPoolExecutor`), modelos de Machine Learning para clasificación y predicción, generación de resúmenes con un modelo de lenguaje (LLM) y un modelo estrella exportado a Power BI, que es el dashboard oficial del proyecto.

Desarrollado para la materia Gestión de la Información de la Universidad Tecnológica de Panamá (UTP), el sistema combina ingesta desde APIs públicas (WAQI y Open-Meteo), almacenamiento en CSV y SQLite, feature engineering, un clasificador Random Forest de categoría AQI (con manejo de clases desbalanceadas mediante `class_weight='balanced'` y validación cruzada no estratificada), predicción de PM2.5 a 24 horas con regresión lineal y un modelo estrella (`exportar_powerbi.py`) que alimenta los dashboards de Power BI.

---

## Instalación

```bash
git clone <URL_DEL_REPOSITORIO>
cd Monitor-de-Calidad-del-Aire-y-Datos-Ambientales
pip install -r requirements.txt
```

Luego configura las claves de API como variables de entorno:

```bash
WAQI_TOKEN=<TU_TOKEN_WAQI>
GROQ_API_KEY=<TU_API_KEY_GROQ>
```

Tambien puedes crear un archivo `.env` en la raiz del proyecto con esos mismos valores. Open-Meteo no requiere clave.

---

## Como obtener las API keys

| Servicio | Para que sirve | Donde obtenerla | Costo |
|----------|----------------|-----------------|-------|
| WAQI | Datos de calidad del aire (AQI, PM2.5, PM10, etc.) | https://aqicn.org/data-platform/token/ | Gratuito |
| Groq | Resumenes y alertas con Llama 3.1 | https://console.groq.com/ | Gratuito |
| Open-Meteo | Datos climaticos | No requiere clave | Gratuito |

1. WAQI: entra a https://aqicn.org/data-platform/token/, registrate con tu correo y recibiras un token para `WAQI_TOKEN`.
2. Groq: crea una cuenta en https://console.groq.com/, ve a API Keys, genera una clave y guardala como `GROQ_API_KEY`.

---

## Uso

### 1. Ejecutar el pipeline de datos

```bash
# Correr al menos 3 veces para acumular datos historicos suficientes
python -m pipeline.actualizar --now
```

### 2. Entrenar el clasificador

```bash
python -m models.clasificador
```

### 3. Exportar el modelo estrella para Power BI

```bash
python exportar_powerbi.py
```

Genera las tablas de hechos y dimensiones en `data/processed/modelo_estrella/` (CSV) y, si `openpyxl` está instalado, en `data/processed/modelo_estrella_powerbi.xlsx`. Abre `Modelo Estrella - Calidad del Aire en América Latina.pbix` en Power BI Desktop y actualiza los datos (Inicio → Actualizar) para refrescar los dashboards.

---

## Estructura del proyecto

```text
Monitor-de-Calidad-del-Aire-y-Datos-Ambientales/
├── config.py              # Configuración central: claves, ciudades, umbrales AQI y rutas
├── requirements.txt
├── README.md
├── FUNCIONALIDADES.md     # Lista detallada de todas las funcionalidades (ver más abajo)
├── pipeline/
│   ├── __init__.py
│   ├── ingesta_waqi.py    # Ingesta de calidad del aire (WAQI) con ThreadPoolExecutor
│   ├── ingesta_clima.py   # Ingesta de clima (Open-Meteo) con ThreadPoolExecutor
│   ├── preprocesar.py     # Limpieza, fusión y feature engineering
│   └── actualizar.py      # Orquestador con scheduler
├── models/
│   ├── __init__.py
│   ├── clasificador.py    # Random Forest de categoría AQI
│   └── prediccion.py      # Predicción PM2.5 24h (regresión lineal)
├── llm/
│   ├── __init__.py
│   └── resumenes.py       # Resúmenes y alertas con Groq
├── exportar_powerbi.py    # Genera el modelo estrella (6 tablas) para Power BI
├── Modelo Estrella - Calidad del Aire en América Latina.pbix  # Dashboard Power BI
├── data/
│   ├── raw/                  # JSON crudos de las APIs
│   └── processed/            # CSV, SQLite, modelos, predicciones y modelo estrella
└── notebooks/
    └── exploracion.ipynb  # Análisis exploratorio
```

---

## Documentación detallada

Para una lista completa y desglosada de todas las funcionalidades implementadas (ingesta, preprocesamiento, modelos, dashboard, etc.), consulta el archivo [FUNCIONALIDADES.md](FUNCIONALIDADES.md).

---


---

## Repositorios de referencia

- [oajetunm/air-quality-dashboard](https://github.com/oajetunm/air-quality-dashboard): organizacion de extraccion y presentacion de datos AQI.
- [jimdowling/air_quality](https://github.com/jimdowling/air_quality): arquitectura de pipeline con actualizacion periodica.
- [Rxghav1103/Real-Time-AQI-Prediction-Using-Machine-Learning](https://github.com/Rxghav1103/Real-Time-AQI-Prediction-Using-Machine-Learning): estructura de pipeline de sklearn para entrenamiento, evaluacion y serializacion del modelo.
- [Alphawarrior21/VayuAssist](https://github.com/Alphawarrior21/VayuAssist): integracion de LLM con datos ambientales para construir prompts y presentar resultados.

Mapa interactivo basado en el enfoque del articulo [Building a Live Weather and AQI Map App with Python and Streamlit](https://medium.com/@preet.balaji20/building-a-live-weather-and-aqi-map-app-with-python-and-streamlit-979cee283843).

---

## Grupo 6 - UTP

Proyecto academico de la materia Gestion de la Informacion.
- Edwin Hou
- Emanuel Gonzalez
- Edward Camaño
- David Pimentel
- Fernando Lezcano