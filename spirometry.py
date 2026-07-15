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
        return "badge-roja", "Patrón obstructivo (FEV1/FVC < 70%)"
    if rendimiento_pct >= 80:
        return "badge-verde", "Función pulmonar normal"
    if rendimiento_pct >= 50:
        return "badge-amarillo", "Patrón obstructivo leve / alerta"
    return "badge-roja", "Restricción severa / emergencia"


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


def back_extrapolar_t0(tiempo, flujo, volumen, idx_pef):
    """
    Extrapolación retroactiva ATS/ERS: traza la tangente en el punto de PEF
    (pendiente máxima de la curva volumen-tiempo) y la proyecta hacia atrás
    hasta cruzar el volumen previo al soplido. Ese cruce fija t0 con más
    precisión que el simple cruce del umbral de inicio.

    tiempo, flujo, volumen: arreglos de la señal completa (sin recortar),
    para poder ver el tramo previo al umbral de inicio detectado.
    idx_pef: índice del PEF dentro de esos mismos arreglos completos.

    Devuelve (t0, volumen_extrapolado): t0 en las mismas unidades que
    `tiempo`, y volumen_extrapolado (Vbe, en L) = volumen en el t0 original
    (cruce de umbral) menos el volumen en el t0 corregido.
    """
    pendiente = flujo[idx_pef]
    if pendiente <= 0:
        return float(tiempo[idx_pef]), 0.0

    t_pef = tiempo[idx_pef]
    v_pef = volumen[idx_pef]
    # Recta tangente: V(t) = v_pef + pendiente * (t - t_pef). Se busca dónde
    # cruza el volumen previo al soplido (el mínimo antes del PEF).
    idx_previos = np.where(tiempo <= t_pef)[0]
    v_base = float(np.min(volumen[idx_previos])) if len(idx_previos) > 0 else float(volumen[0])
    t0 = float(t_pef - (v_pef - v_base) / pendiente)
    t0 = max(t0, float(tiempo[0]))
    return t0, v_base


def evaluar_aceptabilidad(tiempo_rel, flujo_rel, volumen_rel, tiempo_en_pef, fet, volumen_extrapolado, fvc):
    """
    Heurística de aceptabilidad de la maniobra siguiendo criterios ATS/ERS,
    incluyendo el volumen de extrapolación real calculado por
    back_extrapolar_t0 (Vbe < 5% del FVC o < 150 mL, el que sea mayor).
    Devuelve (aceptable, motivo); motivo es None si es aceptable.
    """
    limite_extrapolacion = max(config.EXTRAPOLACION_MAX_PCT_FVC * fvc, config.EXTRAPOLACION_MAX_ABSOLUTA_L)
    if volumen_extrapolado > limite_extrapolacion:
        return False, "Extrapolación de volumen excesiva (arranque impreciso)"

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


def evaluar_repetibilidad(intentos):
    """
    Repetibilidad ATS/ERS entre maniobras: la diferencia entre los dos
    mejores FVC de la sesión no debe superar REPETIBILIDAD_MAX_DIFERENCIA_FVC_L.
    Devuelve (repetible, diferencia_fvc_l); repetible es None si hay menos
    de 2 intentos (no evaluable todavía).
    """
    if len(intentos) < 2:
        return None, None
    fvc_ordenados = sorted((i["fvc"] for i in intentos), reverse=True)
    diferencia = fvc_ordenados[0] - fvc_ordenados[1]
    return diferencia <= config.REPETIBILIDAD_MAX_DIFERENCIA_FVC_L, float(diferencia)


def resumir_sesion(intentos, pef_teorico):
    """
    Dada la lista de intentos de una sesión, decide cuál tiene el mejor PEF y
    cuál el mejor FVC (no necesariamente el mismo intento, según el estándar
    clínico), evalúa repetibilidad entre maniobras, y compone el resumen.
    Devuelve (idx_mejor_pef, idx_mejor_fvc, resumen).
    """
    idx_mejor_pef = max(range(len(intentos)), key=lambda i: intentos[i]["pef_real"])
    idx_mejor_fvc = max(range(len(intentos)), key=lambda i: intentos[i]["fvc"])

    mejor_pef = intentos[idx_mejor_pef]
    mejor_fvc = intentos[idx_mejor_fvc]
    rendimiento_pct = mejor_pef["rendimiento_pct"]
    clase_badge, texto_diag = clasificar_diagnostico(rendimiento_pct, mejor_fvc["fev1_fvc_pct"])
    repetible, diferencia_fvc = evaluar_repetibilidad(intentos)

    resumen = {
        "pef_real": mejor_pef["pef_real"],
        "pef_teorico": pef_teorico,
        "fvc": mejor_fvc["fvc"],
        "fev1": mejor_fvc["fev1"],
        "fev1_fvc_pct": mejor_fvc["fev1_fvc_pct"],
        "fef25_75": mejor_fvc["fef25_75"],
        "rendimiento_pct": rendimiento_pct,
        "clase_badge": clase_badge,
        "texto_diagnostico": texto_diag,
        "repetible": repetible,
        "diferencia_fvc": diferencia_fvc,
    }
    return idx_mejor_pef, idx_mejor_fvc, resumen


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
    idx_inicio_umbral = int(sobre_umbral[0]) if len(sobre_umbral) > 0 else 0

    if len(flujo[idx_inicio_umbral:]) == 0:
        raise ValueError("No se detectó soplido por encima del umbral de inicio.")

    # PEF se busca en toda la señal desde el umbral hasta el final, sobre los
    # arreglos SIN recortar, porque back_extrapolar_t0 necesita ver el tramo
    # previo al cruce de umbral para trazar la tangente.
    idx_pef_absoluto = idx_inicio_umbral + int(np.argmax(flujo[idx_inicio_umbral:]))
    t0, v_base = back_extrapolar_t0(tiempo, flujo, volumen, idx_pef_absoluto)
    volumen_extrapolado = float(volumen[idx_inicio_umbral] - v_base)

    idx_inicio = int(np.searchsorted(tiempo, t0))
    tiempo_rel = tiempo[idx_inicio:] - t0
    flujo_rel = flujo[idx_inicio:]
    volumen_rel = volumen[idx_inicio:] - v_base

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
        tiempo_rel, flujo_rel, volumen_rel, tiempo_en_pef, fet, volumen_extrapolado, fvc
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
        "volumen_extrapolado": volumen_extrapolado,
        "rendimiento_pct": rendimiento_pct,
        "clase_badge": clase_badge,
        "texto_diagnostico": texto_diag,
        "aceptable": aceptable,
        "motivo_no_aceptable": motivo_no_aceptable,
    }
