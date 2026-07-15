"""
Historial clínico persistido en SQLite (espirometro.db), con la misma
jerarquía que el prototipo original en JSON: cada paciente tiene varias
sesiones de espirometría, y cada sesión agrupa varios intentos (maniobras),
siguiendo el estándar clínico de reportar el mejor PEF y el mejor FVC/FEV1
entre todos los intentos, no necesariamente del mismo.

Las curvas completas y el detalle de cada intento (arreglos de cientos de
puntos, no útiles para filtrar por SQL) se guardan serializados en una sola
columna; los campos que sí tiene sentido consultar (fecha, PEF, FVC) quedan
como columnas propias.
"""
import json
import sqlite3
from datetime import datetime

import spirometry

RUTA_DB = "espirometro.db"


def _conectar():
    conexion = sqlite3.connect(RUTA_DB)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def inicializar_db():
    with _conectar() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS pacientes (
                dni TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                edad INTEGER NOT NULL,
                sexo TEXT NOT NULL,
                estatura INTEGER NOT NULL,
                tabaquismo TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sesiones (
                id_sesion TEXT PRIMARY KEY,
                dni TEXT NOT NULL REFERENCES pacientes(dni) ON DELETE CASCADE,
                fecha TEXT NOT NULL,
                pef_teorico REAL NOT NULL,
                mejor_pef_intento INTEGER,
                mejor_fvc_intento INTEGER,
                resumen_json TEXT
            );

            CREATE TABLE IF NOT EXISTS intentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_sesion TEXT NOT NULL REFERENCES sesiones(id_sesion) ON DELETE CASCADE,
                numero INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                pef_real REAL NOT NULL,
                fvc REAL NOT NULL,
                datos_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sesiones_dni ON sesiones(dni);
            CREATE INDEX IF NOT EXISTS idx_intentos_sesion ON intentos(id_sesion);
        """)


inicializar_db()


def guardar_paciente(datos):
    """Crea o actualiza los datos demográficos de un paciente, preservando sus sesiones previas."""
    with _conectar() as con:
        con.execute(
            """
            INSERT INTO pacientes (dni, nombre, edad, sexo, estatura, tabaquismo)
            VALUES (:dni, :nombre, :edad, :sexo, :estatura, :tabaquismo)
            ON CONFLICT(dni) DO UPDATE SET
                nombre=excluded.nombre, edad=excluded.edad, sexo=excluded.sexo,
                estatura=excluded.estatura, tabaquismo=excluded.tabaquismo
            """,
            datos,
        )
    return cargar_paciente(datos["dni"])


def _cargar_sesiones(con, dni):
    filas_sesion = con.execute(
        "SELECT * FROM sesiones WHERE dni = ? ORDER BY fecha", (dni,)
    ).fetchall()

    sesiones = []
    for fila in filas_sesion:
        filas_intento = con.execute(
            "SELECT datos_json FROM intentos WHERE id_sesion = ? ORDER BY numero", (fila["id_sesion"],)
        ).fetchall()
        sesiones.append({
            "id_sesion": fila["id_sesion"],
            "fecha": fila["fecha"],
            "pef_teorico": fila["pef_teorico"],
            "mejor_pef_intento": fila["mejor_pef_intento"],
            "mejor_fvc_intento": fila["mejor_fvc_intento"],
            "resumen": json.loads(fila["resumen_json"]) if fila["resumen_json"] else None,
            "intentos": [json.loads(fi["datos_json"]) for fi in filas_intento],
        })
    return sesiones


def cargar_paciente(dni):
    with _conectar() as con:
        fila = con.execute("SELECT * FROM pacientes WHERE dni = ?", (dni,)).fetchone()
        if fila is None:
            return None
        registro = dict(fila)
        registro["sesiones"] = _cargar_sesiones(con, dni)
        return registro


def listar_pacientes():
    with _conectar() as con:
        filas = con.execute("SELECT * FROM pacientes ORDER BY nombre").fetchall()
        return [dict(fila, sesiones=_cargar_sesiones(con, fila["dni"])) for fila in filas]


def crear_sesion(dni, pef_teorico, fecha=None):
    """Crea una nueva sesión de espirometría (vacía de intentos) y devuelve su id.

    `fecha` es opcional: si se omite, usa el momento actual. Permite registrar
    una sesión con fecha/hora distinta (ej. una prueba histórica en papel que
    se digitaliza después) sin afectar ni sobrescribir sesiones existentes,
    ya que cada una tiene su propio id_sesion independiente.
    """
    fecha = fecha or datetime.now().isoformat(timespec="seconds")
    id_sesion = fecha
    with _conectar() as con:
        existe = con.execute("SELECT 1 FROM pacientes WHERE dni = ?", (dni,)).fetchone()
        if existe is None:
            raise ValueError(f"No existe un paciente registrado con DNI {dni}")

        # id_sesion es la propia fecha (igual que en el formato JSON anterior);
        # si dos sesiones coincidieran al segundo, se desambigua con un sufijo.
        sufijo = 0
        id_candidato = id_sesion
        while con.execute("SELECT 1 FROM sesiones WHERE id_sesion = ?", (id_candidato,)).fetchone():
            sufijo += 1
            id_candidato = f"{id_sesion}-{sufijo}"
        id_sesion = id_candidato

        con.execute(
            "INSERT INTO sesiones (id_sesion, dni, fecha, pef_teorico) VALUES (?, ?, ?, ?)",
            (id_sesion, dni, fecha, pef_teorico),
        )
    return id_sesion


def _recalcular_resumen(con, id_sesion):
    """Delega en spirometry.resumir_sesion la decisión clínica de mejor PEF/FVC
    y repetibilidad, y guarda el resultado en la sesión persistida."""
    fila_sesion = con.execute("SELECT pef_teorico FROM sesiones WHERE id_sesion = ?", (id_sesion,)).fetchone()
    filas_intento = con.execute(
        "SELECT numero, datos_json FROM intentos WHERE id_sesion = ? ORDER BY numero", (id_sesion,)
    ).fetchall()
    intentos = [json.loads(fi["datos_json"]) for fi in filas_intento]

    idx_mejor_pef, idx_mejor_fvc, resumen = spirometry.resumir_sesion(intentos, fila_sesion["pef_teorico"])

    for i, intento in enumerate(intentos):
        intento["es_mejor_pef"] = i == idx_mejor_pef
        intento["es_mejor_fvc"] = i == idx_mejor_fvc
        con.execute(
            "UPDATE intentos SET datos_json = ? WHERE id_sesion = ? AND numero = ?",
            (json.dumps(intento), id_sesion, intento["numero"]),
        )

    con.execute(
        "UPDATE sesiones SET mejor_pef_intento = ?, mejor_fvc_intento = ?, resumen_json = ? WHERE id_sesion = ?",
        (intentos[idx_mejor_pef]["numero"], intentos[idx_mejor_fvc]["numero"], json.dumps(resumen), id_sesion),
    )


def agregar_intento(dni, id_sesion, intento):
    """Agrega un intento (maniobra) a una sesión existente y recompone su resumen."""
    with _conectar() as con:
        existe = con.execute("SELECT 1 FROM sesiones WHERE id_sesion = ? AND dni = ?", (id_sesion, dni)).fetchone()
        if existe is None:
            raise ValueError(f"No existe la sesión {id_sesion} para el paciente {dni}")

        con.execute(
            "INSERT INTO intentos (id_sesion, numero, fecha, pef_real, fvc, datos_json) VALUES (?, ?, ?, ?, ?, ?)",
            (id_sesion, intento["numero"], intento["fecha"], intento["pef_real"], intento["fvc"], json.dumps(intento)),
        )
        _recalcular_resumen(con, id_sesion)

    return cargar_paciente(dni)
