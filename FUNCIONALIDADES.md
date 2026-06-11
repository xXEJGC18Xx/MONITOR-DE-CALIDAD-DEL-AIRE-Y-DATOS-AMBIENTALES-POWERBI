# Funcionalidades del Monitor de Calidad del Aire y Datos Ambientales de America Latina

Este documento lista las funcionalidades implementadas en el programa, separadas por componente.

## 1. Configuracion general

- Carga variables de entorno desde `.env` usando `python-dotenv`.
- Lee la clave `WAQI_TOKEN` para consultar datos de calidad del aire.
- Lee la clave `GROQ_API_KEY` para generar resumenes y alertas con LLM.
- Define el modelo LLM usado: `llama-3.1-8b-instant`.
- Define el maximo de tokens para respuestas LLM: `300`.
- Crea automaticamente las carpetas de datos si no existen:
  - `data/`
  - `data/raw/`
  - `data/processed/`
- Centraliza rutas importantes:
  - `data/processed/datos.csv`
  - `data/processed/ambiental.db`
  - `data/processed/clasificador.pkl`
- Mantiene una lista centralizada de ciudades monitoreadas con latitud, longitud e identificador WAQI.
- Clasifica valores AQI usando umbrales EPA.
- Devuelve categoria, color y nivel de riesgo para cada AQI.
- Maneja valores AQI nulos, invalidos o fuera de rango.
- Considera valores AQI mayores a 500 como categoria peligrosa.

## 2. Ciudades monitoreadas

El sistema monitorea ciudades de America Latina configuradas en `config.py`:

- Ciudad de Panama
- Salvador de Bahia
- Rio de Janeiro
- Sao Paulo
- Cali
- Bogota
- Medellin
- San Jose
- Buenos Aires
- Asuncion
- Quito
- Guayaquil
- Ciudad de Mexico
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

- Nombre de ciudad.
- Latitud.
- Longitud.
- Identificador de estacion o geolocalizacion para WAQI.

## 3. Ingesta de calidad del aire con WAQI

- Consulta la API publica de WAQI.
- Usa el endpoint `https://api.waqi.info/feed/{waqi_id}/`.
- Agrega el token WAQI a cada solicitud.
- Consulta AQI por ciudad.
- Extrae contaminantes desde el bloque `iaqi`.
- Extrae PM2.5.
- Extrae PM10.
- Extrae CO.
- Extrae O3.
- Extrae NO2.
- Extrae SO2.
- Extrae temperatura reportada por WAQI.
- Extrae humedad reportada por WAQI.
- Genera timestamp UTC para cada registro.
- Normaliza la respuesta de WAQI a un diccionario plano.
- Devuelve `None` si la ciudad no existe en la configuracion.
- Si WAQI responde con estado distinto de `ok`, conserva un registro con campos nulos.
- Maneja errores de red sin detener todo el pipeline.
- Maneja errores de parseo JSON o estructura inesperada.
- Registra logs informativos por ciudad consultada.
- Registra logs de advertencia cuando WAQI no devuelve datos validos.
- Registra logs de error cuando hay fallos de red o procesamiento.
- Consulta todas las ciudades configuradas.
- Ejecuta las consultas de ciudades en paralelo con `ThreadPoolExecutor`.
- Limita la concurrencia a un maximo de 8 workers.
- Mantiene el orden final de registros segun el orden de `CIUDADES`.
- Guarda el crudo consolidado en `data/raw/waqi_YYYYMMDDTHHMMSS.json`.
- Devuelve un `pandas.DataFrame` consolidado con una fila por ciudad.
- Puede ejecutarse directamente como modulo/script para imprimir el DataFrame WAQI.

## 4. Ingesta de clima con Open-Meteo

- Consulta la API publica de Open-Meteo.
- No requiere API key.
- Usa el endpoint `https://api.open-meteo.com/v1/forecast`.
- Consulta datos climaticos por latitud y longitud.
- Solicita datos horarios para:
  - Temperatura a 2 metros.
  - Humedad relativa a 2 metros.
  - Velocidad del viento a 10 metros.
  - Precipitacion.
  - Codigo de clima.
  - Temperatura aparente.
- Usa zona horaria `America/Panama` para la consulta de clima.
- Solicita pronostico de 1 dia.
- Busca la lectura horaria mas cercana a la hora actual.
- Genera timestamp UTC para cada registro.
- Normaliza la respuesta en un diccionario plano.
- Extrae temperatura.
- Extrae temperatura aparente.
- Extrae humedad.
- Extrae velocidad del viento en km/h.
- Extrae precipitacion en mm.
- Extrae codigo de clima.
- Maneja listas faltantes o incompletas en la respuesta de Open-Meteo.
- Maneja errores de red sin detener todo el pipeline.
- Maneja errores de parseo o estructura inesperada.
- Consulta todas las ciudades configuradas.
- Ejecuta las consultas de ciudades en paralelo con `ThreadPoolExecutor`.
- Limita la concurrencia a un maximo de 8 workers.
- Mantiene el orden final de registros segun el orden de `CIUDADES`.
- Guarda el crudo consolidado en `data/raw/clima_YYYYMMDDTHHMMSS.json`.
- Devuelve un `pandas.DataFrame` consolidado con una fila por ciudad.
- Puede ejecutarse directamente como modulo/script para imprimir el DataFrame de clima.

## 5. Preprocesamiento y fusion de datos

- Busca los archivos crudos mas recientes de WAQI en `data/raw/`.
- Busca los archivos crudos mas recientes de clima en `data/raw/`.
- Carga los archivos JSON crudos mas recientes como DataFrames.
- Fusiona datos de WAQI y clima por la columna `ciudad`.
- Usa fusion externa (`outer`) para no perder ciudades si una fuente falla.
- Si faltan datos WAQI, conserva datos de clima.
- Si faltan datos de clima, conserva datos WAQI.
- Evita duplicar columnas comunes entre WAQI y clima.
- Cuando hay columnas duplicadas, conserva la version de WAQI.
- Convierte `timestamp` a datetime con zona horaria UTC.
- Elimina filas con mas del 50% de valores nulos.
- Interpola columnas numericas faltantes de forma lineal.
- Interpola en ambas direcciones para completar huecos al inicio o final.
- Genera feature temporal `hora_del_dia`.
- Genera feature temporal `dia_semana`.
- Genera feature binaria `es_fin_de_semana`.
- Genera feature temporal `mes`.
- Calcula `categoria_aqi` usando los umbrales AQI.
- Calcula `color_aqi` para visualizaciones.
- Calcula `riesgo_salud` con valores:
  - `0`: sin riesgo alto.
  - `1`: riesgo para grupos sensibles.
  - `2`: riesgo alto.
- Guarda el dataset procesado en CSV.
- Hace append sobre el CSV existente.
- Elimina duplicados en CSV usando la combinacion `ciudad` + `timestamp`.
- Conserva la ultima version cuando hay duplicados.
- Guarda datos procesados en SQLite.
- Inserta registros en la tabla `lecturas`.
- Maneja errores de escritura en CSV.
- Maneja errores de escritura en SQLite.
- Puede ejecutarse directamente para cargar, fusionar, procesar, guardar e imprimir el resultado.

## 6. Orquestacion del pipeline

- Ejecuta el pipeline ETL completo.
- Ejecuta ingesta WAQI.
- Ejecuta ingesta de clima.
- Fusiona ambas fuentes.
- Preprocesa el dataset fusionado.
- Guarda resultados procesados.
- Registra inicio y fin de cada paso.
- Mide duracion de cada paso.
- Captura errores por paso sin detener inmediatamente todo el programa.
- Si ambas ingestas fallan, aborta la fusion.
- Usa DataFrames vacios como respaldo cuando una fuente falla.
- Permite ejecucion inmediata con:
  - `python -m pipeline.actualizar --now`
- Permite ejecucion programada sin `--now`.
- En modo programado, corre una primera vez inmediatamente.
- En modo programado, repite el pipeline cada hora usando `schedule`.
- Mantiene un ciclo continuo revisando tareas pendientes.
- Provee ayuda de linea de comandos con `--help`.

## 7. Clasificador de categoria AQI

- Entrena un clasificador de categoria AQI con scikit-learn.
- Lee datos desde `data/processed/datos.csv`.
- Valida que exista el CSV procesado antes de entrenar.
- Usa como variables predictoras:
  - PM2.5.
  - PM10.
  - CO.
  - O3.
  - Temperatura.
  - Humedad.
  - Hora del dia.
  - Dia de la semana.
- Usa como variable objetivo `categoria_aqi`.
- Elimina filas con valores faltantes en features o target.
- Valida que existan al menos 2 clases para entrenar.
- Divide datos en entrenamiento y prueba con `train_test_split` y `stratify=None` (sin estratificación) para permitir clases con muy pocas muestras (como categorías dañinas).
- Usa `random_state=42` para reproducibilidad.
- Construye un pipeline de ML con:
  - `StandardScaler`.
  - `RandomForestClassifier` con `class_weight='balanced'` para dar mayor peso a las clases minoritarias.
- Optimiza hiperparámetros con `GridSearchCV`.
- Prueba `n_estimators` de 100 y 200.
- Prueba `max_depth` de 5, 10 y `None`.
- Usa validación cruzada con `KFold` (no estratificada) y `scoring='balanced_accuracy'` para manejar adecuadamente el desbalance de clases.
- Ajusta el número de folds de forma adaptativa (máximo 3) para evitar errores con datasets pequeños.
- Entrena el mejor modelo encontrado.
- Calcula `balanced_accuracy` (internamente durante la búsqueda) y accuracy estándar en el conjunto de prueba.
- Genera `classification_report` (con soporte real de cada clase).
- Imprime mejores hiperparámetros.
- Imprime accuracy.
- Imprime reporte de clasificación.
- Guarda el modelo entrenado en `data/processed/clasificador.pkl`.
- Puede predecir la categoria AQI para un diccionario de features.
- Carga automaticamente el modelo entrenado para predecir.
- Devuelve `None` si se intenta predecir sin modelo entrenado.
- Calcula importancia de features del Random Forest.
- Devuelve importancias en un DataFrame ordenado.
- Devuelve `None` si se piden importancias sin modelo entrenado.
- Puede ejecutarse directamente para entrenar y mostrar importancias.

## 8. Prediccion de PM2.5 a 24 horas

- Predice PM2.5 para las proximas 24 horas.
- Lee datos historicos desde `data/processed/datos.csv`.
- Filtra datos por ciudad.
- Convierte timestamps a datetime UTC.
- Ordena datos historicos por tiempo.
- Descarta filas sin timestamp o PM2.5.
- Valida que haya al menos 2 registros para predecir.
- Usa Prophet si esta disponible.
- Configura Prophet con estacionalidad multiplicativa.
- Activa estacionalidad diaria en Prophet.
- Genera un DataFrame futuro de 24 horas.
- Predice `yhat`, `yhat_lower` y `yhat_upper`.
- Si Prophet no esta disponible, usa regresion lineal.
- Si Prophet esta disponible pero falla, cae automaticamente a regresion lineal.
- El fallback lineal usa como features:
  - Hora del dia.
  - Dia de la semana.
- Genera features temporales si no existen.
- Entrena `LinearRegression`.
- Calcula margen aproximado usando desviacion estandar de residuales.
- Usa margen de 5.0 si solo hay un residual.
- Genera las proximas 24 marcas horarias desde la ultima lectura.
- Evita predicciones negativas usando `np.clip`.
- Devuelve columnas:
  - `hora`
  - `pm25_predicho`
  - `lower`
  - `upper`
- Guarda predicciones por ciudad en `data/processed/predicciones_{ciudad}.csv`.
- Maneja errores de guardado de predicciones.
- Puede ejecutarse directamente para predecir la primera ciudad configurada.

## 9. Generacion de resumenes y alertas con LLM

- Inicializa cliente Groq de forma perezosa.
- Usa `GROQ_API_KEY` desde variables de entorno.
- Si no hay clave Groq, usa texto de respaldo.
- Si falta el paquete `groq`, usa texto de respaldo.
- Si el cliente Groq falla, usa texto de respaldo.
- Calcula metricas globales para resumen diario:
  - Ciudad con AQI mas alto.
  - Ciudad con AQI mas bajo.
  - PM2.5 promedio.
  - Cantidad de ciudades con AQI mayor a 100.
- Maneja datasets sin AQI valido.
- Genera resumen diario en espanol sobre calidad del aire en America Latina.
- Pide al LLM un resumen maximo de 150 palabras.
- Incluye estado general de la region.
- Incluye ciudad mas afectada.
- Sugiere posibles causas como trafico, industria o clima.
- Incluye recomendaciones practicas.
- Incluye alerta para grupos vulnerables si corresponde.
- Devuelve solo el resumen, sin explicaciones adicionales.
- Si falla la API, devuelve resumen local de respaldo.
- Genera alertas cortas por ciudad y AQI.
- Pide al LLM una alerta de maximo 40 palabras.
- Si falla la API, devuelve alerta local de respaldo.
- Nunca propaga errores de Groq al dashboard.
- Puede ejecutarse directamente para generar resumen desde el CSV procesado.

## 10. Dashboard Streamlit

- Provee una interfaz web interactiva con Streamlit.
- Configura pagina en layout wide.
- Muestra titulo del monitor ambiental de America Latina.
- Muestra caption institucional.
- Carga datos procesados desde CSV.
- Usa cache de datos con TTL de 300 segundos.
- Convierte timestamp a datetime.
- Convierte columnas numericas criticas:
  - AQI.
  - PM2.5.
  - PM10.
  - CO.
  - O3.
- Muestra advertencia si no hay datos procesados.
- Detiene la app si no hay datos.
- Provee sidebar de filtros.
- Permite filtrar por multiples ciudades.
- Selecciona todas las ciudades por defecto.
- Permite filtrar por rango de fechas.
- Calcula fecha minima y maxima desde el dataset.
- Usa fecha actual si no hay timestamps validos.
- Permite elegir contaminante a graficar:
  - PM2.5.
  - PM10.
  - CO.
  - O3.
- Incluye boton `Actualizar datos`.
- Ejecuta el pipeline completo desde el dashboard.
- Limpia cache de Streamlit despues de actualizar datos.
- Recarga la app despues de actualizar datos.
- Filtra el DataFrame por ciudades seleccionadas.
- Filtra el DataFrame por rango de fechas.
- Muestra advertencia si los filtros no tienen datos.
- Calcula la ultima lectura por ciudad.
- Calcula AQI promedio actual.
- Calcula PM2.5 promedio actual.
- Identifica la ciudad mas contaminada segun AQI.
- Calcula categoria general del AQI promedio.
- Muestra KPI de AQI promedio.
- Muestra KPI de ciudad mas contaminada.
- Muestra KPI de PM2.5 promedio.
- Muestra KPI de categoria general.
- Muestra una barra de color asociada a la categoria general.
- Ajusta estilos visuales para filtros con nombres largos.
- Evita que los nombres largos se corten en el multiselect.
- Ajusta metricas para permitir textos largos.
- Usa mapa Folium centrado en America Latina.
- Usa tiles `CartoDB positron`.
- Limita zoom minimo del mapa.
- Dibuja un circulo por ciudad.
- Coloca cada circulo usando latitud y longitud configuradas.
- Define radio del circulo segun AQI.
- Limita radio minimo y maximo del marcador.
- Usa color de categoria AQI para cada circulo.
- Usa gris cuando no hay datos.
- Muestra popup por ciudad con:
  - Nombre completo.
  - AQI.
  - PM2.5.
  - Categoria.
- Muestra tooltip visible al pasar el cursor por el circulo.
- Da formato al tooltip con fondo blanco, borde, sombra, fuente legible y texto normal.
- Escapa texto HTML de ciudad/categoria para evitar markup inseguro.
- Renderiza mapa con `streamlit-folium`.
- Muestra resumen diario generado por LLM o respaldo local.
- Guarda resumen en `st.session_state`.
- Permite regenerar resumen manualmente.
- Organiza graficas en pestanas.
- Pestana de serie temporal:
  - Grafica evolucion del contaminante seleccionado.
  - Usa linea por ciudad.
  - Usa marcadores.
  - Usa Plotly Express.
  - Muestra mensaje si no hay datos del contaminante.
- Pestana de prediccion 24h:
  - Permite elegir ciudad para predecir.
  - Incluye boton para generar la prediccion bajo demanda.
  - Entrena y predice PM2.5 para esa ciudad.
  - Conserva la ultima prediccion generada en la sesion para evitar recalcular en cada render.
  - Muestra spinner mientras genera prediccion.
  - Muestra mensaje si no hay datos suficientes.
  - Grafica limite superior.
  - Grafica limite inferior.
  - Grafica intervalo de confianza.
  - Grafica PM2.5 predicho con linea y marcadores.
  - Usa Plotly Graph Objects.
- Pestana de importancia de features:
  - Carga importancias desde el clasificador entrenado.
  - Muestra mensaje si el modelo no existe o no tiene datos suficientes.
  - Grafica barras horizontales de importancia.
- Pestana de correlacion:
  - Selecciona columnas numericas.
  - Excluye columnas derivadas no deseadas: `es_fin_de_semana`, `mes`, `riesgo_salud`.
  - Calcula matriz de correlacion.
  - Grafica heatmap con `px.imshow`.
  - Usa escala `RdBu_r`.
  - Muestra valores numericos dentro del heatmap.
  - Muestra mensaje si no hay suficientes variables numericas.
- Muestra seccion de alertas para AQI mayor a 100.
- Filtra ciudades con AQI mayor a 100.
- Muestra mensaje de exito si ninguna ciudad supera AQI 100.
- Muestra tabla de alertas si hay ciudades en riesgo.
- Ordena alertas de mayor a menor AQI.
- Muestra columnas disponibles entre:
  - Ciudad.
  - AQI.
  - PM2.5.
  - Categoria AQI.
  - Riesgo salud.
- Aplica estilos de color por severidad en la tabla:
  - Gris para riesgo nulo/desconocido.
  - Rojo claro para riesgo alto.
  - Naranja claro para riesgo sensible.
  - Amarillo claro para riesgo bajo.

## 11. Persistencia de datos y artefactos

- Guarda respuestas crudas WAQI en JSON.
- Guarda respuestas crudas Open-Meteo en JSON.
- Guarda dataset procesado en CSV.
- Guarda dataset procesado en SQLite.
- Guarda modelo clasificador entrenado en Pickle/Joblib.
- Guarda predicciones PM2.5 por ciudad en CSV.
- Mantiene deduplicacion del CSV procesado.
- Usa nombres de archivo con timestamp para datos crudos.
- Usa nombres de archivo por ciudad para predicciones.

## 12. Manejo de errores y resiliencia

- No detiene todo el pipeline si falla una ciudad.
- No detiene todo el pipeline si falla una fuente y la otra tiene datos.
- Registra errores de red en WAQI.
- Registra errores de red en Open-Meteo.
- Registra errores de parseo.
- Registra errores de escritura de archivos.
- Registra errores de SQLite.
- Registra errores de Prophet y usa regresion lineal como fallback.
- Registra errores de Groq y usa textos locales como fallback.
- Valida datos insuficientes antes de entrenar modelos.
- Valida datos insuficientes antes de predecir.
- Evita romper el dashboard si faltan datos, modelo o API key.

## 13. Automatizacion y ejecucion

- Permite correr el pipeline desde linea de comandos.
- Permite correr el pipeline una sola vez.
- Permite correr el pipeline cada hora.
- Permite ejecutar ingesta WAQI individualmente.
- Permite ejecutar ingesta clima individualmente.
- Permite ejecutar preprocesamiento individualmente.
- Permite entrenar clasificador individualmente.
- Permite ejecutar prediccion individualmente.
- Permite ejecutar resumen LLM individualmente.
- Permite lanzar dashboard interactivo con Streamlit.
- Permite actualizar datos desde el propio dashboard.

## 14. Analisis exploratorio

- Incluye notebook `notebooks/exploracion.ipynb`.
- Documenta como ejecutar el pipeline antes del EDA.
- Importa configuracion central del proyecto.
- Permite cargar datos procesados.
- Permite explorar el dataset generado por el pipeline.
- Sirve como apoyo para analisis y presentacion del proyecto.

## 15. Documentacion del proyecto

- Incluye README con descripcion del sistema.
- Incluye instrucciones de instalacion.
- Incluye instrucciones para configurar API keys.
- Incluye comandos de uso.
- Incluye criterios de evaluacion.
- Incluye estructura del proyecto.
- Incluye repositorios de referencia.
- Incluye este inventario completo de funcionalidades.

## 16. Funcionalidades no implementadas como sistema separado

Estas capacidades aparecen como comportamiento interno o parcial, pero no como modulo independiente:

- No hay autenticacion de usuarios.
- No hay roles ni permisos.
- No hay API REST propia.
- No hay despliegue en nube configurado.
- No hay pruebas unitarias formales en carpeta `tests/`.
- No hay sistema de notificaciones por correo, SMS o mensajeria.
- No hay base de datos relacional con migraciones versionadas.
- No hay historico separado por tablas normalizadas.
- No hay panel administrativo.
- No hay exportacion manual desde el dashboard a Excel o PDF.
