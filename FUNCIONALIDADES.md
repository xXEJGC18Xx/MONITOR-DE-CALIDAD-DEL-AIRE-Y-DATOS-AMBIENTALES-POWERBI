# Funcionalidades del Monitor de Calidad del Aire y Datos Ambientales de América Latina

Este documento lista las funcionalidades implementadas en el programa, separadas por componente. Para una visión general, consulta el [`README.md`](README.md).

## 1. Configuración general

- Carga variables de entorno desde `.env` usando `python-dotenv`.
- Lee la clave `WAQI_TOKEN` para consultar datos de calidad del aire.
- Lee la clave `GROQ_API_KEY` para generar resúmenes y alertas con LLM.
- Define el modelo LLM usado: `llama-3.1-8b-instant`.
- Define el máximo de tokens para respuestas LLM: `300`.
- Crea automáticamente las carpetas de datos si no existen:
  - `data/`
  - `data/raw/`
  - `data/processed/`
- Centraliza rutas importantes:
  - `data/processed/datos.csv`
  - `data/processed/ambiental.db`
  - `data/processed/clasificador.pkl`
- Mantiene una lista centralizada de ciudades monitoreadas con latitud, longitud e identificador WAQI.
- Clasifica valores AQI usando umbrales EPA.
- Devuelve categoría, color y nivel de riesgo para cada AQI.
- Maneja valores AQI nulos, inválidos o fuera de rango.
- Considera valores AQI mayores a 500 como categoría peligrosa.

## 2. Ciudades monitoreadas (27 ciudades con nombres oficiales y tildes)

El sistema monitorea las siguientes ciudades de América Latina (tal como aparecen en `config.py` y en los datos procesados):

- Ciudad de Panamá
- Salvador de Bahia
- Río de Janeiro
- São Paulo
- Cali
- Bogotá
- Medellín
- San José
- Buenos Aires
- Asunción
- Quito
- Guayaquil
- Ciudad de México
- Guadalajara
- Monterrey
- Santiago de Chile
- Coyhaique
- Padre Las Casas
- Los Andes
- Iquique
- Puerto Montt
- Tegucigalpa
- Ciudad de Guatemala
- Lima
- San Salvador
- Managua
- Santo Domingo

Cada ciudad incluye:

- Nombre (con tildes cuando corresponde).
- Latitud.
- Longitud.
- Identificador de estación o geolocalización para WAQI.

## 3. Ingesta de calidad del aire con WAQI

- Consulta la API pública de WAQI.
- Usa el endpoint `https://api.waqi.info/feed/{waqi_id}/`.
- Agrega el token WAQI a cada solicitud.
- Consulta AQI por ciudad.
- Extrae contaminantes desde el bloque `iaqi`.
- Extrae PM2.5, PM10, CO, O3, NO2, SO2.
- Extrae temperatura y humedad reportadas por WAQI.
- Genera timestamp UTC para cada registro.
- Normaliza la respuesta de WAQI a un diccionario plano.
- Devuelve `None` si la ciudad no existe en la configuración.
- Si WAQI responde con estado distinto de `ok`, conserva un registro con campos nulos.
- Maneja errores de red sin detener todo el pipeline.
- Maneja errores de parseo JSON o estructura inesperada.
- Registra logs informativos por ciudad consultada.
- Registra logs de advertencia cuando WAQI no devuelve datos válidos.
- Registra logs de error cuando hay fallos de red o procesamiento.
- Consulta todas las ciudades configuradas **en paralelo** usando `ThreadPoolExecutor` (máximo 8 workers).
- Mantiene el orden final de registros según el orden de `CIUDADES`.
- Guarda el crudo consolidado en `data/raw/waqi_YYYYMMDDTHHMMSS.json`.
- Devuelve un `pandas.DataFrame` consolidado con una fila por ciudad.
- Puede ejecutarse directamente como módulo/script para imprimir el DataFrame WAQI.

## 4. Ingesta de clima con Open-Meteo

- Consulta la API pública de Open-Meteo (sin clave).
- Usa el endpoint `https://api.open-meteo.com/v1/forecast`.
- Consulta datos climáticos por latitud y longitud.
- Solicita datos horarios para:
  - Temperatura a 2 metros.
  - Humedad relativa a 2 metros.
  - Velocidad del viento a 10 metros.
  - Precipitación.
  - Código de clima.
  - Temperatura aparente.
- Usa zona horaria `America/Panama` para la consulta.
- Solicita pronóstico de 1 día.
- Busca la lectura horaria más cercana a la hora actual.
- Genera timestamp UTC para cada registro.
- Normaliza la respuesta en un diccionario plano.
- Extrae temperatura, temperatura aparente, humedad, viento (km/h), precipitación (mm) y código de clima.
- Maneja listas faltantes o incompletas en la respuesta.
- Maneja errores de red sin detener todo el pipeline.
- Maneja errores de parseo o estructura inesperada.
- Consulta todas las ciudades configuradas **en paralelo** con `ThreadPoolExecutor` (máximo 8 workers).
- Mantiene el orden final de registros según el orden de `CIUDADES`.
- Guarda el crudo consolidado en `data/raw/clima_YYYYMMDDTHHMMSS.json`.
- Devuelve un `pandas.DataFrame` consolidado con una fila por ciudad.
- Puede ejecutarse directamente como módulo/script para imprimir el DataFrame de clima.

## 5. Preprocesamiento y fusión de datos

- Busca los archivos crudos más recientes de WAQI y clima en `data/raw/`.
- Carga los archivos JSON crudos más recientes como DataFrames.
- Fusiona datos de WAQI y clima por la columna `ciudad` (fusión externa `outer`).
- Si faltan datos WAQI, conserva datos de clima; viceversa.
- Evita duplicar columnas comunes: cuando hay duplicadas, conserva la versión de WAQI.
- Convierte `timestamp` a datetime con zona horaria UTC.
- Elimina filas con más del 50% de valores nulos.
- Interpola columnas numéricas faltantes de forma lineal (en ambas direcciones).
- Genera características temporales: `hora_del_dia`, `dia_semana`, `es_fin_de_semana`, `mes`.
- Calcula `categoria_aqi`, `color_aqi` y `riesgo_salud` (0: sin riesgo, 1: grupos sensibles, 2: riesgo alto).
- Guarda el dataset procesado en CSV (append + deduplicación por `ciudad`+`timestamp`).
- Guarda los datos procesados en SQLite (tabla `lecturas`, append).
- Maneja errores de escritura en CSV y SQLite.
- Puede ejecutarse directamente para cargar, fusionar, procesar, guardar e imprimir el resultado.

## 6. Orquestación del pipeline

- Ejecuta el pipeline completo: WAQI → clima → fusión → preprocesamiento → guardado → predicción PM2.5 24h (todas las ciudades) → resumen diario LLM.
- Registra inicio, fin y duración de cada paso.
- Captura errores por paso sin detener los demás.
- Si ambas ingestas fallan, aborta la fusión.
- Usa DataFrames vacíos como respaldo cuando una fuente falla.
- Genera la predicción PM2.5 a 24h de **todas** las ciudades configuradas (no solo una), guardando un CSV por ciudad para alimentar `fact_predicciones` en Power BI. Si una ciudad falla, se registra el error y se continúa con las demás.
- Permite ejecución inmediata con `python -m pipeline.actualizar --now`.
- Permite ejecución programada (sin `--now`): corre cada hora usando `schedule` (primera ejecución inmediata).
- Provee ayuda de línea de comandos con `--help`.

## 7. Clasificador de categoría AQI

- Entrena un clasificador Random Forest con scikit-learn.
- Lee datos desde `data/processed/datos.csv`.
- Usa como variables predictoras: PM2.5, PM10, CO, O3, temperatura, humedad, hora_del_dia, dia_semana.
- Variable objetivo: `categoria_aqi`.
- Elimina filas con valores faltantes.
- Valida que existan al menos 2 clases para entrenar.
- Divide en entrenamiento/prueba (80/20) **sin estratificación** (permite clases muy pequeñas).
- Pipeline: `StandardScaler` + `RandomForestClassifier` con `class_weight='balanced'`.
- Optimización con `GridSearchCV` (n_estimators: 100,200; max_depth: 5,10,None).
- Validación cruzada con `KFold` (no estratificada) y scoring `balanced_accuracy`.
- Ajusta número de folds (máximo 3) para datasets pequeños.
- Entrena el mejor modelo y lo guarda en `data/processed/clasificador.pkl`.
- Evalúa con accuracy estándar y classification report.
- Puede predecir categoría AQI para un diccionario de features.
- Calcula importancia de features y las devuelve en un DataFrame ordenado.
- Puede ejecutarse directamente para entrenar y mostrar importancias.

## 8. Predicción de PM2.5 a 24 horas

- Predice PM2.5 para las próximas 24 horas.
- Lee datos históricos desde `data/processed/datos.csv`, filtra por ciudad.
- Convierte timestamp a datetime UTC, ordena y descarta filas sin PM2.5.
- Requiere al menos 2 registros históricos.
- **Método**: Regresión lineal (scikit-learn) usando hora_del_dia y dia_semana como features.
- Calcula un margen de confianza (`lower`/`upper`) a partir de la desviación estándar de los residuales del modelo.
- Evita predicciones negativas con `np.clip`.
- Devuelve DataFrame con columnas: `hora`, `pm25_predicho`, `lower`, `upper`.
- Guarda la predicción en `data/processed/predicciones_{ciudad}.csv`.
- Puede ejecutarse directamente para predecir la primera ciudad configurada.

## 9. Generación de resúmenes y alertas con LLM (Groq)

- Inicializa cliente Groq de forma perezosa.
- Usa `GROQ_API_KEY`; si no existe o falla, usa textos de respaldo.
- Calcula métricas globales para el resumen diario: ciudad con mayor AQI, menor AQI, promedio PM2.5, número de ciudades con AQI > 100.
- Genera resumen diario en español (máx. 150 palabras) pidiendo al LLM incluir: estado general, ciudad más afectada, posibles causas, recomendaciones, alerta para grupos vulnerables si aplica.
- Si falla la API, devuelve un resumen de respaldo local.
- Genera alertas cortas (máx. 40 palabras) por ciudad y AQI.
- Nunca propaga errores de Groq al dashboard.
- Puede ejecutarse directamente para generar resumen desde el CSV procesado.
- Colapsa saltos de línea del texto generado a una sola línea (`_limpiar_texto`), para que el CSV exportado a Power BI no se corrompa.

## 9b. Consultas en lenguaje natural al LLM (`llm/consultas.py`)

- Permite hacer preguntas libres en español sobre el estado actual de la calidad del aire y el clima.
- Arma un resumen de texto con la última lectura de cada ciudad (AQI, categoría, PM2.5, PM10, temperatura, humedad, viento) y se lo pasa al LLM como contexto.
- Instruye al modelo a responder **solo** con base en ese contexto, sin inventar datos.
- Soporta historial de conversación (varias preguntas seguidas manteniendo contexto), acotado a los últimos mensajes.
- Si Groq no está disponible, devuelve el resumen de datos en texto plano en vez de fallar.
- Accesible desde `python menu.py` (opción 4) o directamente con `python -m llm.consultas`.

## 10. Modelo estrella y dashboard Power BI

- `exportar_powerbi.py` construye el modelo estrella a partir de `data/processed/datos.csv` y los CSV auxiliares del pipeline.
- Genera 6 tablas: `fact_lecturas`, `dim_ciudad`, `dim_tiempo`, `dim_categoria_aqi`, `fact_predicciones`, `fact_resumenes`.
- Normaliza nombres de ciudad entre fuentes (mapeo de variantes) para que los `JOIN` en Power BI funcionen correctamente.
- Exporta cada tabla como CSV individual en `data/processed/modelo_estrella/`.
- Exporta también un único Excel (`data/processed/modelo_estrella_powerbi.xlsx`) con una hoja por tabla, si `openpyxl`/`xlsxwriter` están disponibles.
- El dashboard oficial es el archivo `Modelo Estrella - Calidad del Aire en América Latina.pbix` (Power BI Desktop), que se conecta a estas tablas y se actualiza manualmente desde Power BI.

## 11. Persistencia de datos y artefactos

- Guarda respuestas crudas de WAQI y Open-Meteo en JSON (con timestamp).
- Guarda dataset procesado en CSV y SQLite.
- Guarda modelo clasificador entrenado en Pickle/Joblib.
- Guarda predicciones PM2.5 por ciudad en CSV.
- Deduplicación del CSV procesado por `ciudad` + `timestamp`.

## 12. Manejo de errores y resiliencia

- No detiene el pipeline si falla una ciudad o una fuente.
- Registra errores de red, parseo, escritura y SQLite.
- Fallback de Groq a textos locales.
- Validación de datos insuficientes antes de entrenar/predecir.
- La exportación a Power BI omite tablas vacías (predicciones o resúmenes) sin fallar si aún no se generaron.

## 13. Automatización y ejecución

- Ejecución desde línea de comandos: pipeline, ingestas individuales, preprocesamiento, clasificador, predicción, resumen LLM, exportación a Power BI.
- Modo programado (cada hora) y modo único (`--now`).
- **Menú interactivo** (`python menu.py`): centraliza todas las operaciones anteriores en un solo punto de entrada, con submenú para elegir el modo del pipeline (una vez / programado) y una sección de preguntas al LLM.
