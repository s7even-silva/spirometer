"""
Métricas clínicas de espirometría a partir de las curvas de flujo/volumen
ya procesadas, y comparación contra el valor teórico esperado.

`calcular_pef_teorico` reutiliza la ecuación de predicción de Knudson et al.
del prototipo original (SpiroIntelli Pro).
"""
import numpy as np

import config


def calcular_pef_teorico(sexo, edad, estatura):
    if sexo == "Masculino":
        return (0.056 * estatura) - (0.024 * edad) - 2.13
    return (0.041 * estatura) - (0.018 * edad) - 1.25


def clasificar_diagnostico(rendimiento_pct):
    if rendimiento_pct >= 80:
        return "badge-verde", "🟢 Función Pulmonar Normal"
    if rendimiento_pct >= 50:
        return "badge-amarillo", "🟡 Patrón Obstructivo Leve / Alerta"
    return "badge-roja", "🔴 Restricción Severa / Emergencia"


def calcular_metricas(tiempo, flujo, volumen, pef_teorico):
    """
    tiempo, flujo, volumen: arreglos (numpy o listas) de la sesión completa.
    Devuelve un diccionario con las métricas clínicas y curvas ya recortadas
    al inicio real del soplido (para que FVC/FEV1 partan de volumen 0).
    """
    tiempo = np.asarray(tiempo, dtype=float)
    flujo = np.asarray(flujo, dtype=float)
    volumen = np.asarray(volumen, dtype=float)

    sobre_umbral = np.where(flujo >= config.UMBRAL_INICIO_SOPLIDO_L_S)[0]
    idx_inicio = int(sobre_umbral[0]) if len(sobre_umbral) > 0 else 0

    tiempo_rel = tiempo[idx_inicio:] - tiempo[idx_inicio]
    flujo_rel = flujo[idx_inicio:]
    volumen_rel = volumen[idx_inicio:] - volumen[idx_inicio]

    if len(flujo_rel) == 0:
        raise ValueError("No se detectó soplido por encima del umbral de inicio.")

    idx_pef = int(np.argmax(flujo_rel))
    pef_real = float(flujo_rel[idx_pef])
    tiempo_en_pef = float(tiempo_rel[idx_pef])
    volumen_en_pef = float(volumen_rel[idx_pef])

    fvc = float(volumen_rel[-1])
    fev1 = float(np.interp(1.0, tiempo_rel, volumen_rel))
    fev1_fvc_pct = (fev1 / fvc * 100.0) if fvc > 0 else 0.0

    rendimiento_pct = (pef_real / pef_teorico * 100.0) if pef_teorico else 0.0
    clase_badge, texto_diag = clasificar_diagnostico(rendimiento_pct)

    return {
        "tiempo": tiempo_rel.tolist(),
        "flujo": flujo_rel.tolist(),
        "volumen": volumen_rel.tolist(),
        "pef_real": pef_real,
        "tiempo_en_pef": tiempo_en_pef,
        "volumen_en_pef": volumen_en_pef,
        "pef_teorico": pef_teorico,
        "fvc": fvc,
        "fev1": fev1,
        "fev1_fvc_pct": fev1_fvc_pct,
        "rendimiento_pct": rendimiento_pct,
        "clase_badge": clase_badge,
        "texto_diagnostico": texto_diag,
    }
