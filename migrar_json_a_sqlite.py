"""
Migración única de los historiales clínicos en Historiales_Medicos/*.json
(formato anterior) a la base SQLite (espirometro.db). No borra los JSON
originales; se pueden eliminar manualmente después de verificar la migración.
"""
import glob
import json
import os
import sqlite3

import patients

CARPETA_JSON = "Historiales_Medicos"


def migrar():
    if not os.path.isdir(CARPETA_JSON):
        print(f"No existe la carpeta {CARPETA_JSON}, nada que migrar.")
        return

    rutas = sorted(glob.glob(os.path.join(CARPETA_JSON, "*.json")))
    if not rutas:
        print("No hay archivos JSON para migrar.")
        return

    con = patients._conectar()
    migrados, saltados = 0, 0

    for ruta in rutas:
        with open(ruta, "r", encoding="utf-8") as f:
            registro = json.load(f)

        dni = registro["dni"]
        ya_existe = con.execute("SELECT 1 FROM pacientes WHERE dni = ?", (dni,)).fetchone()
        if ya_existe:
            print(f"  {dni}: ya existe en la base, se omite (no se sobrescribe).")
            saltados += 1
            continue

        con.execute(
            "INSERT INTO pacientes (dni, nombre, edad, sexo, estatura, tabaquismo) VALUES (?, ?, ?, ?, ?, ?)",
            (dni, registro["nombre"], registro["edad"], registro["sexo"], registro["estatura"], registro["tabaquismo"]),
        )

        for sesion in registro.get("sesiones", []):
            con.execute(
                """
                INSERT INTO sesiones (id_sesion, dni, fecha, pef_teorico, mejor_pef_intento, mejor_fvc_intento, resumen_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sesion["id_sesion"], dni, sesion["fecha"], sesion["pef_teorico"],
                    sesion.get("mejor_pef_intento"), sesion.get("mejor_fvc_intento"),
                    json.dumps(sesion["resumen"]) if sesion.get("resumen") else None,
                ),
            )
            for intento in sesion.get("intentos", []):
                con.execute(
                    "INSERT INTO intentos (id_sesion, numero, fecha, pef_real, fvc, datos_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (sesion["id_sesion"], intento["numero"], intento["fecha"], intento["pef_real"], intento["fvc"], json.dumps(intento)),
                )

        print(f"  {dni}: migrado ({len(registro.get('sesiones', []))} sesión/es).")
        migrados += 1

    con.commit()
    con.close()
    print(f"\nListo: {migrados} paciente(s) migrado(s), {saltados} omitido(s) por ya existir.")


if __name__ == "__main__":
    migrar()
