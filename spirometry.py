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


def clasificar_diagnostico(rendimiento_pct, fev1_fvc_pct):
    """FEV1/FVC < 70% es el criterio clínico estándar (GOLD) de patrón obstructivo,
    y se evalúa antes que el PEF porque es el indicador más confiable."""
    if fev1_fvc_pct < 70:
        return "badge-roja", "🔴 Patrón Obstructivo (FEV1/FVC < 70%)"
    if rendimiento_pct >= 80:
        return "badge-verde", "🟢 Función Pulmonar Normal"
    if rendimiento_pct >= 50:
        return "badge-amarillo", "🟡 Patrón Obstructivo Leve / Alerta"
    return "badge-roja", "🔴 Restricción Severa / Emergencia"


def calcular_fef25_75(tiempo_rel, volumen_rel, fvc):
    """Flujo espiratorio forzado medio (L/s) entre el 25% y el 75% del FVC.

    Se interpola el tiempo en que se alcanza cada volumen objetivo (orden de
    argumentos invertido respecto a FEV1: aquí el eje x de la interpolación
    es volumen_rel, no tiempo_rel).
    """
    if fvc <= 0:
        return 0.0
    vol_25, vol_75 = 0.25 * fvc, 0.75 * fvc
    t_25 = np.interp(vol_25, volumen_rel, tiempo_rel)
    t_75 = np.interp(vol_75, volumen_rel, tiempo_rel)
    return float((vol_75 - vol_25) / (t_75 - t_25)) if t_75 > t_25 else 0.0


def calcular_fet(tiempo_rel):
    """Tiempo espiratorio forzado (s): duración de la señal ya recortada al soplido activo."""
    return float(tiempo_rel[-1]) if len(tiempo_rel) > 0 else 0.0


def evaluar_aceptabilidad(tiempo_rel, flujo_rel, volumen_rel, tiempo_en_pef, fet):
    """
    Heurística simplificada de aceptabilidad de la maniobra (no sustituye el
    back-extrapolation volumétrico completo del estándar ATS/ERS).
    Devuelve (aceptable, motivo); motivo es None si es aceptable.
    """
    if fet < config.FET_MINIMO_ACEPTABLE_S:
        return False, "Duración insuficiente"

    ventana = tiempo_rel[-1] - config.VENTANA_MESETA_S
    idx_meseta = np.searchsorted(tiempo_rel, ventana)
    if idx_meseta < len(volumen_rel) - 1:
        cambio_meseta = volumen_rel[-1] - volumen_rel[idx_meseta]
        if cambio_meseta > config.TOLERANCIA_MESETA_VOLUMEN_L:
            return False, "Sin meseta de fin de espiración"

    if idx_meseta > 0 and np.any(flujo_rel[:idx_meseta] < config.FLUJO_MINIMO_INTERRUPCION_L_S):
        return False, "Posible interrupción o tos"

    if tiempo_en_pef > config.TIEMPO_MAXIMO_PEF_ACEPTABLE_S:
        return False, "Arranque lento, esfuerzo insuficiente"

    return True, None


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
    fef25_75 = calcular_fef25_75(tiempo_rel, volumen_rel, fvc)
    fet = calcular_fet(tiempo_rel)

    rendimiento_pct = (pef_real / pef_teorico * 100.0) if pef_teorico else 0.0
    clase_badge, texto_diag = clasificar_diagnostico(rendimiento_pct, fev1_fvc_pct)
    aceptable, motivo_no_aceptable = evaluar_aceptabilidad(
        tiempo_rel, flujo_rel, volumen_rel, tiempo_en_pef, fet
    )

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
        "fef25_75": fef25_75,
        "fet": fet,
        "rendimiento_pct": rendimiento_pct,
        "clase_badge": clase_badge,
        "texto_diagnostico": texto_diag,
        "aceptable": aceptable,
        "motivo_no_aceptable": motivo_no_aceptable,
    }
