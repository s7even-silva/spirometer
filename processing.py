"""
Conversión de la señal cruda del sensor (diferencia de presión, Pa) a
flujo (L/s) y volumen (L), aplicando las constantes definidas en config.py.

Modelo físico: tubo tipo Venturi/Pitot con restricción (régimen turbulento):

    Q = Cd * A2 * sqrt( 2*|ΔP| / (ρ * (1 - β^4)) )      [m³/s]

donde β = D2/D1 (garganta/entrada), A2 es el área de la garganta y ρ es la
densidad del aire. El signo de Q sigue el signo de ΔP para soportar flujo
bidireccional (inspiración/espiración).
"""
import math
from collections import deque

import numpy as np

import config

R_AIRE_SECO = 287.058   # J/(kg·K)
R_VAPOR_AGUA = 461.495  # J/(kg·K)
MMHG_POR_PA = 1 / 133.322


def presion_vapor_saturacion_pa(temp_c):
    """Presión de vapor de saturación del agua (ecuación de Tetens), en Pa."""
    return 610.78 * 10 ** (7.5 * temp_c / (237.3 + temp_c))


def calcular_densidad_aire(temp_c=None, presion_kpa=None, humedad_pct=None):
    """Densidad del aire húmedo (kg/m³) a partir de temperatura, presión y humedad."""
    if config.DENSIDAD_AIRE_MANUAL_KG_M3 is not None:
        return config.DENSIDAD_AIRE_MANUAL_KG_M3

    temp_c = config.TEMPERATURA_AMBIENTE_C if temp_c is None else temp_c
    presion_kpa = config.PRESION_ATMOSFERICA_KPA if presion_kpa is None else presion_kpa
    humedad_pct = config.HUMEDAD_RELATIVA_PCT if humedad_pct is None else humedad_pct

    temp_k = temp_c + 273.15
    presion_total_pa = presion_kpa * 1000.0
    presion_vapor_pa = (humedad_pct / 100.0) * presion_vapor_saturacion_pa(temp_c)
    presion_seca_pa = presion_total_pa - presion_vapor_pa

    return (presion_seca_pa / (R_AIRE_SECO * temp_k)) + (presion_vapor_pa / (R_VAPOR_AGUA * temp_k))


def _area_garganta_m2():
    d2_m = config.DIAMETRO_GARGANTA_MM / 1000.0
    return math.pi / 4.0 * d2_m ** 2


def _beta():
    return config.DIAMETRO_GARGANTA_MM / config.DIAMETRO_ENTRADA_MM


def presion_a_flujo(delta_p_pa, rho):
    """Convierte una diferencia de presión (Pa) a flujo (L/s), con signo."""
    if delta_p_pa == 0:
        return 0.0

    beta = _beta()
    denominador = rho * (1 - beta ** 4)
    signo = 1.0 if delta_p_pa > 0 else -1.0
    caudal_m3_s = config.COEFICIENTE_DESCARGA_CD * _area_garganta_m2() * math.sqrt(
        2 * abs(delta_p_pa) / denominador
    )
    return signo * caudal_m3_s * 1000.0  # m³/s -> L/s


def flujo_a_presion(q_l_s, rho):
    """Inversa de presion_a_flujo: útil para generar señales de prueba/simulación."""
    if q_l_s == 0:
        return 0.0

    beta = _beta()
    denominador = rho * (1 - beta ** 4)
    signo = 1.0 if q_l_s > 0 else -1.0
    q_m3_s = abs(q_l_s) / 1000.0
    delta_p_pa = (q_m3_s / (config.COEFICIENTE_DESCARGA_CD * _area_garganta_m2())) ** 2 * denominador / 2.0
    return signo * delta_p_pa


def suavizar_senal(valores, ventana=None):
    """Media móvil aplicada a un arreglo completo (uso en reprocesamiento final)."""
    ventana = config.VENTANA_FILTRO_MEDIA_MOVIL if ventana is None else ventana
    valores = np.asarray(valores, dtype=float)
    if ventana <= 1 or len(valores) == 0:
        return valores
    kernel = np.ones(ventana) / ventana
    return np.convolve(valores, kernel, mode="same")


class FiltroMediaMovil:
    """Media móvil incremental para suavizar la señal muestra a muestra (streaming en vivo)."""

    def __init__(self, ventana=None):
        self.ventana = config.VENTANA_FILTRO_MEDIA_MOVIL if ventana is None else ventana
        self._buffer = deque(maxlen=self.ventana)

    def filtrar(self, valor):
        self._buffer.append(valor)
        return sum(self._buffer) / len(self._buffer)


def integrar_volumen(flujos_l_s, dt=None):
    """Integración trapezoidal acumulada del flujo (L/s) para obtener volumen (L)."""
    dt = config.SAMPLE_INTERVAL_S if dt is None else dt
    flujos = np.asarray(flujos_l_s, dtype=float)
    if len(flujos) == 0:
        return np.array([])
    incrementos = (flujos[:-1] + flujos[1:]) / 2.0 * dt
    return np.concatenate(([0.0], np.cumsum(incrementos)))


def factor_btps(temp_ambiente_c=None, presion_atm_kpa=None):
    """Factor de corrección ATPS -> BTPS para el volumen exhalado."""
    temp_ambiente_c = config.TEMPERATURA_AMBIENTE_C if temp_ambiente_c is None else temp_ambiente_c
    presion_atm_kpa = config.PRESION_ATMOSFERICA_KPA if presion_atm_kpa is None else presion_atm_kpa

    pb_mmhg = presion_atm_kpa * 1000.0 * MMHG_POR_PA
    ph2o_ambiente_mmhg = presion_vapor_saturacion_pa(temp_ambiente_c) * MMHG_POR_PA
    ph2o_corporal_mmhg = presion_vapor_saturacion_pa(config.BTPS_TEMP_CORPORAL_C) * MMHG_POR_PA

    temp_ambiente_k = temp_ambiente_c + 273.15
    temp_corporal_k = config.BTPS_TEMP_CORPORAL_C + 273.15

    return ((pb_mmhg - ph2o_ambiente_mmhg) / (pb_mmhg - ph2o_corporal_mmhg)) * (temp_corporal_k / temp_ambiente_k)


def aplicar_btps(volumen_l):
    """Aplica la corrección BTPS a un arreglo de volumen (L), si está habilitada."""
    volumen_l = np.asarray(volumen_l, dtype=float)
    if not config.APLICAR_BTPS:
        return volumen_l
    return volumen_l * factor_btps()
