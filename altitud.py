"""
Estimación automática de la presión atmosférica local a partir de la
geolocalización aproximada por IP (sin API key, precisión de ciudad, no de
ubicación exacta) y la fórmula barométrica internacional.

Solo se usa como valor por defecto sugerido al arrancar el servidor: el
operador siempre puede corregirlo a mano desde la interfaz si conoce la
altitud real del consultorio (más preciso que cualquier estimación por IP).
"""
import logging

import requests

logger = logging.getLogger(__name__)

PRESION_NIVEL_MAR_KPA = 101.325
TIMEOUT_S = 3.0


def _presion_desde_altitud(altitud_m):
    """Fórmula barométrica internacional (aproximación troposférica estándar)."""
    return PRESION_NIVEL_MAR_KPA * (1 - 2.25577e-5 * altitud_m) ** 5.25588


def detectar_ubicacion_por_ip():
    """
    Consulta un servicio gratuito de geolocalización por IP. Devuelve un dict
    con ciudad, altitud estimada (m) y presión atmosférica estimada (kPa), o
    None si no hay conexión o el servicio falla.
    """
    try:
        resp = requests.get("http://ip-api.com/json/?fields=status,city,lat,lon", timeout=TIMEOUT_S)
        datos = resp.json()
        if datos.get("status") != "success":
            logger.warning("Geolocalización por IP no disponible: %s", datos.get("message", "respuesta inválida"))
            return None

        lat, lon = datos["lat"], datos["lon"]
        elev_resp = requests.get(
            "https://api.open-elevation.com/api/v1/lookup", params={"locations": f"{lat},{lon}"}, timeout=TIMEOUT_S
        )
        altitud_m = elev_resp.json()["results"][0]["elevation"]
        presion_kpa = _presion_desde_altitud(altitud_m)

        logger.info(
            "Ubicación detectada por IP: %s (%.4f, %.4f), altitud %.0fm, presión estimada %.3f kPa",
            datos.get("city", "?"), lat, lon, altitud_m, presion_kpa,
        )
        return {"ciudad": datos.get("city", "Desconocida"), "altitud_m": altitud_m, "presion_kpa": presion_kpa}
    except (requests.RequestException, KeyError, ValueError, IndexError) as error:
        logger.warning("No se pudo detectar la ubicación por IP: %s", error)
        return None
