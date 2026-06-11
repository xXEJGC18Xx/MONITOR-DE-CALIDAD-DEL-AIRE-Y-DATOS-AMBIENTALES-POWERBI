# Monitor de Calidad del Aire y Datos Ambientales de America Latina

Sistema integral de monitoreo ambiental que recopila, procesa y analiza la calidad del aire y las condiciones climaticas de ciudades clave de America Latina. El proyecto integra un pipeline de datos automatizado, modelos de Machine Learning para clasificacion y prediccion, generacion de resumenes con un modelo de lenguaje (LLM) y un dashboard interactivo construido con Streamlit.

Desarrollado para la materia Gestion de la Informacion de la Universidad Tecnologica de Panama (UTP), el sistema combina ingesta desde APIs publicas (WAQI y Open-Meteo), almacenamiento en CSV y SQLite, feature engineering, un clasificador Random Forest de categoria AQI, prediccion de PM2.5 a 24 horas con fallback a regresion lineal y visualizacion geoespacial con mapas Folium.

---

## Instalacion

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

### 3. Lanzar el dashboard

```bash
streamlit run dashboard/app.py
```

El dashboard se abre automaticamente en `http://localhost:8501`.

---

## Criterios de evaluacion

| Criterio | Componente del proyecto | Peso |
|----------|-------------------------|------|
| Pipeline de datos | Ingesta (WAQI + Open-Meteo), preprocesamiento y orquestacion | 30% |
| Analisis con Machine Learning | Clasificador Random Forest + prediccion PM2.5 a 24h | 25% |
| Dashboard interactivo | Streamlit con mapas, KPIs y graficas | 25% |
| Documentacion | README, docstrings y notebook de exploracion | 20% |

---

## Estructura del proyecto

```text
Monitor-de-Calidad-del-Aire-y-Datos-Ambientales/
├── config.py              # Configuracion central: claves, ciudades, umbrales AQI y rutas
├── requirements.txt
├── README.md
├── pipeline/
│   ├── ingesta_waqi.py    # Ingesta de calidad del aire (WAQI)
│   ├── ingesta_clima.py   # Ingesta de clima (Open-Meteo)
│   ├── preprocesar.py     # Limpieza, fusion y feature engineering
│   └── actualizar.py      # Orquestador con scheduler
├── models/
│   ├── clasificador.py    # Random Forest de categoria AQI
│   └── prediccion.py      # Prediccion PM2.5 24h (Prophet / fallback lineal)
├── llm/
│   └── resumenes.py       # Resumenes y alertas con Groq
├── dashboard/
│   └── app.py             # Dashboard Streamlit
├── data/
│   ├── raw/               # JSON crudos de las APIs
│   └── processed/         # CSV, SQLite, modelos y predicciones
└── notebooks/
    └── exploracion.ipynb  # Analisis exploratorio
```

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
