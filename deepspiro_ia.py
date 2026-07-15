"""
Integración con DeepSpiro (COPD-Early-Prediction/): detección de patrón
obstructivo y predicción de riesgo futuro a partir de la curva de un
intento de espirometría ya procesado por nuestro propio pipeline.

DeepSpiro espera la curva de volumen exhalado acumulado (no el flujo, pese
al nombre del campo 'flow' en su formato original) muestreada a 100 Hz, en
mL, más FEV1/FVC en litros y edad/sexo/tabaquismo del paciente. Todo eso ya
existe en nuestro pipeline (spirometry.calcular_metricas, patients), así
que la integración es un mapeo de formato, no una reimplementación.

Los modelos se cargan una sola vez (perezosamente, en el primer uso) y se
cachean en memoria: son pesados de instanciar (red neuronal + 2 modelos
CatBoost) pero baratos de ejecutar por muestra.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_RUTA_DEEPSPIRO = os.path.join(os.path.dirname(__file__), "COPD-Early-Prediction")
_UMBRAL_DETECCION = 0.1  # mismo valor por defecto que run_predict.py

_modelos = None  # cacheado tras la primera carga exitosa; None si falló


def _cargar_modelos():
    """Carga los tres modelos de DeepSpiro. Devuelve None si algo falla (pesos
    ausentes, dependencias no instaladas, etc.) sin interrumpir el arranque
    del resto de la aplicación: la IA es un complemento, no una dependencia
    crítica del flujo clínico existente."""
    global _modelos
    if _modelos is not None:
        return _modelos

    if _RUTA_DEEPSPIRO not in sys.path:
        sys.path.insert(0, _RUTA_DEEPSPIRO)

    try:
        import torch
        from utils.predict_utils import load_spiro_encoder, load_cb_model

        device_str = "cuda" if torch.cuda.is_available() else "cpu"
        device = torch.device(device_str)

        encoder = load_spiro_encoder(
            device_str=device_str,
            model_path=os.path.join(_RUTA_DEEPSPIRO, "weights", "SpiroEncoder.pth"),
        )
        explainer = load_cb_model(os.path.join(_RUTA_DEEPSPIRO, "weights", "SpiroExplainer.cbm"))
        predictor = load_cb_model(os.path.join(_RUTA_DEEPSPIRO, "weights", "SpiroPredictor.cbm"))

        _modelos = {"device": device, "encoder": encoder, "explainer": explainer, "predictor": predictor}
        logger.info("Modelos DeepSpiro cargados correctamente (device=%s)", device_str)
    except Exception:
        logger.exception("No se pudieron cargar los modelos DeepSpiro; la predicción por IA quedará deshabilitada")
        _modelos = False

    return _modelos or None


def _mapear_sexo(sexo_texto):
    return 1 if sexo_texto == "Masculino" else 0


def _mapear_tabaquismo(tabaquismo_texto):
    return 1 if tabaquismo_texto == "Fumador" else 0


def _construir_entrada(intento, paciente):
    """Arma el mismo formato de fila que preprocess_data() espera de un CSV/
    Excel, pero directamente en memoria a partir de nuestros propios datos,
    sin escribir ningún archivo intermedio."""
    volumen_l = np.asarray(intento["volumen"], dtype=float)
    volumen_ml = np.round(volumen_l * 1000).astype(int)
    serie_csv = ",".join(str(v) for v in volumen_ml)

    row = pd.Series({
        "flow": serie_csv,
        "pef": "",
        "fev1": intento["fev1"],
        "fvc": intento["fvc"],
    })
    return row


def predecir(intento, paciente):
    """
    Ejecuta el pipeline DeepSpiro completo (SpiroEncoder -> SpiroExplainer,
    y SpiroPredictor si no se detecta COPD activo) sobre un intento ya
    calculado por spirometry.calcular_metricas.

    Devuelve un dict con el resultado, o {"disponible": False, "motivo": ...}
    si los modelos no pudieron cargarse o la curva no es válida para el
    modelo (ej. demasiado corta). Nunca lanza excepción hacia el llamador:
    un fallo de la IA no debe interrumpir el flujo clínico ya validado.
    """
    modelos = _cargar_modelos()
    if modelos is None:
        return {"disponible": False, "motivo": "Modelos de IA no disponibles en este servidor."}

    try:
        from utils.predict_utils import (
            process_data, process_acceleration, run_spiro_encoder, run_spiro_explainer, run_spiro_predictor,
        )

        row = _construir_entrada(intento, paciente)
        row = process_data(row)
        row = process_acceleration(row)

        datos = pd.Series(dtype="float64")
        datos["flow_volume"] = row["flow_volume"]
        datos["PEF_FEF25"] = row["PEF_FEF25"].values[0]
        datos["FEF25_FEF50"] = row["FEF25_FEF50"].values[0]
        datos["FEF50_FEF75"] = row["FEF50_FEF75"].values[0]
        datos["FEF75"] = row["FEF75"].values[0]
        datos["PEF_FEF75"] = row["PEF_FEF75"].values[0]
        datos["TOTAL"] = row["TOTAL"].values[0]
        datos["AGE"] = paciente["edad"]
        datos["SEX"] = _mapear_sexo(paciente["sexo"])
        datos["smoke"] = _mapear_tabaquismo(paciente["tabaquismo"])
        datos["blow_ratio"] = 1 - (row["FEV1"] / row["FVC"])
        datos["fef25"] = row["blow_fef25"]
        datos["fef50"] = row["blow_fef50"]
        datos["fef75"] = row["blow_fef75"]
        datos["FEV1"] = row["FEV1"]
        datos["FVC"] = row["FVC"]

        encoder_result, attention_weights, all_input_x = run_spiro_encoder(
            model=modelos["encoder"], data=datos, device=modelos["device"]
        )

        deteccion, imagen_base64 = run_spiro_explainer(
            model=modelos["explainer"],
            data=datos,
            threshold=_UMBRAL_DETECCION,
            spiro_encoder_original_result=encoder_result,
            attention_weights=attention_weights,
            all_input_x=all_input_x,
            is_show=False,
        )
        deteccion = bool(deteccion)

        riesgo_futuro = None
        if not deteccion:
            probabilidades = run_spiro_predictor(model=modelos["predictor"], data=datos)
            riesgo_futuro = [float(p) for p in probabilidades[0][1:6]]

        return {
            "disponible": True,
            "copd_detectado": deteccion,
            "score_encoder": float(encoder_result[0][0][1]),
            "riesgo_1_5_anios": riesgo_futuro,
            "imagen_atencion_base64": imagen_base64,
        }
    except Exception as error:
        logger.exception("Error al ejecutar la predicción DeepSpiro")
        return {"disponible": False, "motivo": f"Error al procesar la curva: {error}"}
