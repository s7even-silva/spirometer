"""
Historial clínico persistido como un archivo JSON por paciente
(carpeta Historiales_Medicos/<dni>.json), igual que el prototipo original
pero acumulando el historial de pruebas de cada paciente en vez de solo
guardar al paciente activo en memoria.
"""
import json
import os
from datetime import datetime

CARPETA_DB = "Historiales_Medicos"


def _ruta(dni):
    return os.path.join(CARPETA_DB, f"{dni}.json")


def _asegurar_carpeta():
    os.makedirs(CARPETA_DB, exist_ok=True)


def guardar_paciente(datos):
    """Crea o actualiza los datos demográficos de un paciente, preservando sus pruebas previas."""
    _asegurar_carpeta()
    dni = datos["dni"]
    registro = cargar_paciente(dni) or {"pruebas": []}
    registro.update(datos)
    registro.setdefault("pruebas", [])
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


def agregar_resultado_prueba(dni, resultado):
    """Agrega un resultado de prueba de espirometría al historial del paciente."""
    registro = cargar_paciente(dni)
    if registro is None:
        raise ValueError(f"No existe un paciente registrado con DNI {dni}")

    resultado_guardado = dict(resultado)
    resultado_guardado["fecha"] = datetime.now().isoformat(timespec="seconds")
    registro.setdefault("pruebas", []).append(resultado_guardado)

    with open(_ruta(dni), "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)
    return registro
