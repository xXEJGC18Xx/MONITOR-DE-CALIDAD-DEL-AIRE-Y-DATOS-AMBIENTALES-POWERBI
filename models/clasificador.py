"""
models/clasificador.py
======================
Clasificador de la categoría AQI usando Random Forest dentro de un Pipeline
de scikit-learn (escalado + modelo), optimizado con GridSearchCV.

Referencia de estructura de entrenamiento/serialización:
https://github.com/Rxghav1103/Real-Time-AQI-Prediction-Using-Machine-Learning
"""

import logging
from math import ceil

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config import CSV_PROCESADO, MODELO_CLASIFICADOR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Features y target usados por el clasificador.
FEATURES = ["pm25", "pm10", "co", "o3", "temperatura",
            "humedad", "hora_del_dia", "dia_semana"]
TARGET = "categoria_aqi"


def entrenar_clasificador():
    """
    Entrena el clasificador de categoría AQI a partir de data/processed/datos.csv.

    Construye un Pipeline (StandardScaler + RandomForestClassifier con class_weight='balanced'),
    optimiza hiperparámetros con GridSearchCV usando KFold (no estratificado) y scoring de
    'balanced_accuracy' para manejar clases desbalanceadas (incluyendo categorías dañinas
    con pocas muestras). Imprime accuracy estándar y classification report, y serializa
    el mejor modelo en data/processed/clasificador.pkl.

    La división train/test se realiza sin estratificación para permitir clases con
    una sola instancia.

    Retorna
    -------
    tuple[sklearn.pipeline.Pipeline, dict]
        (modelo_entrenado, métricas). Si no hay datos suficientes retorna (None, {}).
    """
   
    """Entrena el clasificador sin eliminar clases raras."""
    if not CSV_PROCESADO.exists():
        logger.error("No existe %s. Ejecute primero el pipeline.", CSV_PROCESADO)
        return None, {}

    df = pd.read_csv(CSV_PROCESADO)
    columnas = FEATURES + [TARGET]
    df = df.dropna(subset=columnas)

    if df.empty or df[TARGET].nunique() < 2:
        logger.error("Datos insuficientes o menos de 2 clases para entrenar.")
        return None, {}

    X = df[FEATURES]
    y = df[TARGET]

    # --- 1. División simple sin estratificación (permite clases con 1 muestra) ---
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=None
    )

    # Verificar que haya al menos 2 clases en entrenamiento y que cada una tenga al menos 1 muestra
    if y_train.nunique() < 2:
        logger.error("Entrenamiento con una sola clase, no se puede entrenar.")
        return None, {}

    # --- 2. Pipeline con clase balanced ---
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("rf", RandomForestClassifier(random_state=42, class_weight='balanced')),
    ])

    # --- 3. GridSearchCV con validación cruzada simple (no estratificada) ---
    #    Usamos KFold normal (no StratifiedKFold) para evitar errores con clases raras
    from sklearn.model_selection import KFold
    param_grid = {
        "rf__n_estimators": [100, 200],
        "rf__max_depth": [5, 10, None],
    }
    # Número de folds: no puede superar el tamaño de la clase más pequeña, pero como no estratificamos,
    # podemos usar un valor fijo pequeño. Si alguna clase tiene 1 muestra, KFold normal igual partirá
    # los datos sin respetar clases, lo cual es aceptable para validación.
    cv_folds = min(3, len(X_train))  # máximo 3 folds
    if cv_folds < 2:
        logger.error("Muy pocos datos para validación cruzada.")
        return None, {}

    kfold = KFold(n_splits=cv_folds, shuffle=True, random_state=42)
    grid = GridSearchCV(pipeline, param_grid, cv=kfold, n_jobs=-1, scoring="balanced_accuracy")
    grid.fit(X_train, y_train)

    modelo = grid.best_estimator_
    y_pred = modelo.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    reporte = classification_report(y_test, y_pred, zero_division=0)

    print(f"\nMejores hiperparámetros: {grid.best_params_}")
    print(f"Accuracy en test: {acc:.4f}\n")
    print("Classification report:")
    print(reporte)

    joblib.dump(modelo, MODELO_CLASIFICADOR)
    logger.info("Modelo guardado en %s", MODELO_CLASIFICADOR)

    metricas = {
        "accuracy": acc,
        "best_params": grid.best_params_,
        "classification_report": reporte,
    }
    return modelo, metricas

def predecir(datos_dict):
    """
    Predice la categoría AQI para un conjunto de features dado.

    Parámetros
    ----------
    datos_dict : dict
        Diccionario con los valores de los features definidos en FEATURES.

    Retorna
    -------
    str | None
        Categoría AQI predicha como texto, o None si el modelo no existe.
    """
    if not MODELO_CLASIFICADOR.exists():
        logger.error("No existe el modelo. Entrene primero con entrenar_clasificador().")
        return None

    modelo = joblib.load(MODELO_CLASIFICADOR)
    fila = pd.DataFrame([{f: datos_dict.get(f) for f in FEATURES}])
    prediccion = modelo.predict(fila)[0]
    return str(prediccion)


def get_feature_importance():
    """
    Devuelve la importancia de cada feature del clasificador entrenado.

    Retorna
    -------
    pandas.DataFrame | None
        DataFrame con columnas 'feature' e 'importancia', ordenado de mayor
        a menor. None si el modelo no existe.
    """
    if not MODELO_CLASIFICADOR.exists():
        logger.error("No existe el modelo para extraer importancias.")
        return None

    modelo = joblib.load(MODELO_CLASIFICADOR)
    rf = modelo.named_steps["rf"]
    importancias = pd.DataFrame({
        "feature": FEATURES,
        "importancia": rf.feature_importances_,
    }).sort_values("importancia", ascending=False).reset_index(drop=True)
    return importancias


if __name__ == "__main__":
    modelo, metricas = entrenar_clasificador()
    if modelo is not None:
        print("\n=== Importancia de features ===")
        print(get_feature_importance().to_string(index=False))
