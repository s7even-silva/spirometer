"""
Curvas de flujo sintéticas para el modo de simulación, parametrizadas por
perfil clínico. Cada perfil define un flujo objetivo en L/s (magnitud
fisiológica), nunca una presión: la conversión a presión la hace siempre
processing.flujo_a_presion, así que la simulación sigue siendo válida sin
importar la geometría del tubo o la densidad del aire configuradas.
"""
import math

PERFILES = {
    "sano": {"pef_l_s": 7.8, "t_pico_s": 0.3, "duracion_s": 4.0, "forma_cola": 1.0},
    "copd": {"pef_l_s": 4.2, "t_pico_s": 0.45, "duracion_s": 8.0, "forma_cola": 0.55},
}


def flujo_objetivo_l_s(perfil, t_relativo):
    """Flujo instantáneo (L/s) del perfil dado en el instante t_relativo (s) desde el inicio del soplido."""
    parametros = PERFILES[perfil]
    if t_relativo < 0 or t_relativo > parametros["duracion_s"]:
        return 0.0
    x = t_relativo / parametros["t_pico_s"]
    return parametros["pef_l_s"] * x * math.exp(parametros["forma_cola"] * (1 - x))
