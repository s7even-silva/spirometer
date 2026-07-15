"""
Curvas de flujo sintéticas para el modo de simulación, parametrizadas por
perfil clínico. Cada perfil define un flujo objetivo en L/s (magnitud
fisiológica), nunca una presión: la conversión a presión la hace siempre
processing.flujo_a_presion, así que la simulación sigue siendo válida sin
importar la geometría del tubo o la densidad del aire configuradas.

El perfil "copd" usa una forma bi-exponencial (decaimiento rápido inicial +
una cola lenta de menor peso, que representa el vaciado lento de vías
pequeñas obstruidas) en vez de una única cola de decaimiento lento: esa
forma más simple daba un FVC clínicamente irreal (>10L) al intentar bajar
el FEV1/FVC por debajo del 70%, muy fuera del rango típico (3-6L) para el
que fue entrenado el modelo DeepSpiro de predicción de EPOC.
"""
import math

PERFILES = {
    "sano": {"pef_l_s": 7.8, "t_pico_s": 0.3, "duracion_s": 4.0, "forma_cola": 1.0},
    "copd": {"pef_l_s": 4.0, "t_pico_s": 0.45, "duracion_s": 9.0, "tau_cola_s": 2.3, "peso_cola": 0.4},
}


def flujo_objetivo_l_s(perfil, t_relativo):
    """Flujo instantáneo (L/s) del perfil dado en el instante t_relativo (s) desde el inicio del soplido."""
    parametros = PERFILES[perfil]
    if t_relativo < 0 or t_relativo > parametros["duracion_s"]:
        return 0.0

    if perfil == "copd":
        return _flujo_copd(t_relativo, parametros)

    x = t_relativo / parametros["t_pico_s"]
    return parametros["pef_l_s"] * x * math.exp(parametros["forma_cola"] * (1 - x))


def _flujo_copd(t_relativo, parametros):
    pef = parametros["pef_l_s"]
    t_pico = parametros["t_pico_s"]
    x = t_relativo / t_pico
    if t_relativo <= t_pico:
        return pef * x * math.exp(1 - x)

    peso_cola = parametros["peso_cola"]
    decaimiento_rapido = math.exp(-(t_relativo - t_pico) / 0.45)
    cola_lenta = math.exp(-t_relativo / parametros["tau_cola_s"]) * peso_cola
    return pef * (decaimiento_rapido * (1 - peso_cola) + cola_lenta)
