"""
Historial clínico persistido como un archivo JSON por paciente
(carpeta Historiales_Medicos/<dni>.json), igual que el prototipo original
pero acumulando el historial de sesiones de espirometría de cada paciente en
vez de solo guardar al paciente activo en memoria. Cada sesión agrupa varios
intentos (maniobras), siguiendo el estándar clínico de reportar el mejor PEF
y el mejor FVC/FEV1 entre todos los intentos, no necesariamente del mismo.
"""
import json
import os
from datetime import datetime

import spirometry

CARPETA_DB = "Historiales_Medicos"


def _ruta(dni):
    return os.path.join(CARPETA_DB, f"{dni}.json")


def _asegurar_carpeta():
    os.makedirs(CARPETA_DB, exist_ok=True)


def guardar_paciente(datos):
    """Crea o actualiza los datos demográficos de un paciente, preservando sus sesiones previas."""
    _asegurar_carpeta()
    dni = datos["dni"]
    registro = cargar_paciente(dni) or {"sesiones": []}
    registro.update(datos)
    registro.setdefault("sesiones", [])
    with open(_ruta(dni), "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)
    return registro


def cargar_paciente(dni):
    ruta = _ruta(dni)
    if not os.path.exists(ruta):
        return None
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def listar_pacientes():
    _asegurar_carpeta()
    pacientes = []
    for nombre_archivo in sorted(os.listdir(CARPETA_DB)):
        if nombre_archivo.endswith(".json"):
            with open(os.path.join(CARPETA_DB, nombre_archivo), "r", encoding="utf-8") as f:
                pacientes.append(json.load(f))
    return pacientes


def crear_sesion(dni, pef_teorico):
    """Crea una nueva sesión de espirometría (vacía de intentos) y devuelve su id."""
    registro = cargar_paciente(dni)
    if registro is None:
        raise ValueError(f"No existe un paciente registrado con DNI {dni}")

    id_sesion = datetime.now().isoformat(timespec="seconds")
    sesion = {
        "id_sesion": id_sesion,
        "fecha": id_sesion,
        "pef_teorico": pef_teorico,
        "intentos": [],
        "mejor_pef_intento": None,
        "mejor_fvc_intento": None,
        "resumen": None,
    }
    registro.setdefault("sesiones", []).append(sesion)

    with open(_ruta(dni), "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)
    return id_sesion


def _recalcular_resumen(sesion):
    """Recalcula, sobre todos los intentos de la sesión, cuál tiene el mejor PEF y
    cuál el mejor FVC (no necesariamente el mismo), y compone el resumen clínico."""
    intentos = sesion["intentos"]

    idx_mejor_pef = max(range(len(intentos)), key=lambda i: intentos[i]["pef_real"])
    idx_mejor_fvc = max(range(len(intentos)), key=lambda i: intentos[i]["fvc"])

    for i, intento in enumerate(intentos):
        intento["es_mejor_pef"] = i == idx_mejor_pef
        intento["es_mejor_fvc"] = i == idx_mejor_fvc

    sesion["mejor_pef_intento"] = intentos[idx_mejor_pef]["numero"]
    sesion["mejor_fvc_intento"] = intentos[idx_mejor_fvc]["numero"]

    mejor_pef = intentos[idx_mejor_pef]
    mejor_fvc = intentos[idx_mejor_fvc]
    rendimiento_pct = mejor_pef["rendimiento_pct"]
    clase_badge, texto_diag = spirometry.clasificar_diagnostico(rendimiento_pct, mejor_fvc["fev1_fvc_pct"])

    sesion["resumen"] = {
        "pef_real": mejor_pef["pef_real"],
        "pef_teorico": sesion["pef_teorico"],
        "fvc": mejor_fvc["fvc"],
        "fev1": mejor_fvc["fev1"],
        "fev1_fvc_pct": mejor_fvc["fev1_fvc_pct"],
        "fef25_75": mejor_fvc["fef25_75"],
        "rendimiento_pct": rendimiento_pct,
        "clase_badge": clase_badge,
        "texto_diagnostico": texto_diag,
    }


def agregar_intento(dni, id_sesion, intento):
    """Agrega un intento (maniobra) a una sesión existente y recompone su resumen."""
    registro = cargar_paciente(dni)
    if registro is None:
        raise ValueError(f"No existe un paciente registrado con DNI {dni}")

    sesion = next((s for s in registro.get("sesiones", []) if s["id_sesion"] == id_sesion), None)
    if sesion is None:
        raise ValueError(f"No existe la sesión {id_sesion} para el paciente {dni}")

    sesion["intentos"].append(intento)
    _recalcular_resumen(sesion)

    with open(_ruta(dni), "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)
    return registro
