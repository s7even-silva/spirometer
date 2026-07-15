"""
Servidor Flask del espirómetro: sirve la página web local, gestiona el
historial clínico y coordina, vía Socket.IO, la captura en vivo de una
sesión de espirometría (con varios intentos) a partir de la lectura
continua del puerto serial.
"""
import argparse
import logging
import queue
import threading
from datetime import datetime

import numpy as np
from flask import Flask, redirect, render_template, request, session, url_for
from flask_socketio import SocketIO

import config
import patients
import processing
import spirometry
from logging_config import configurar_logging
from serial_reader import lector

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "spiroIntelli-dev-secret"  # solo para uso local
socketio = SocketIO(app, async_mode="threading")

sesiones_activas = {}  # sid -> {"detener", "id_sesion", "siguiente_numero_intento"}


# =====================================================================
# Rutas HTTP
# =====================================================================
@app.route("/")
def index():
    return redirect(url_for("historial"))


@app.route("/historial", methods=["GET", "POST"])
def historial():
    if request.method == "POST":
        datos = {
            "dni": request.form["dni"].strip(),
            "nombre": request.form["nombre"].strip(),
            "edad": int(request.form["edad"]),
            "sexo": request.form["sexo"],
            "estatura": int(request.form["estatura"]),
            "tabaquismo": request.form["tabaquismo"],
        }
        patients.guardar_paciente(datos)
        session["paciente_dni"] = datos["dni"]
        return redirect(url_for("historial"))

    dni_activo = session.get("paciente_dni")
    return render_template(
        "historial.html",
        pacientes=patients.listar_pacientes(),
        paciente_activo=patients.cargar_paciente(dni_activo) if dni_activo else None,
        pagina_activa="historial",
    )


@app.route("/historial/seleccionar/<dni>", methods=["POST"])
def seleccionar_paciente(dni):
    if patients.cargar_paciente(dni) is not None:
        session["paciente_dni"] = dni
    return redirect(url_for("historial"))


@app.route("/prueba")
def prueba():
    dni_activo = session.get("paciente_dni")
    paciente = patients.cargar_paciente(dni_activo) if dni_activo else None
    if paciente is None:
        return redirect(url_for("historial"))

    pef_teorico = spirometry.calcular_pef_teorico(paciente["sexo"], paciente["edad"], paciente["estatura"])
    return render_template(
        "prueba.html",
        paciente=paciente,
        pef_teorico=pef_teorico,
        pagina_activa="prueba",
    )


# =====================================================================
# Captura en vivo por Socket.IO
# =====================================================================
def ejecutar_captura(sid, dni, id_sesion, numero_intento, pef_teorico):
    try:
        _ejecutar_captura_interno(sid, dni, id_sesion, numero_intento, pef_teorico)
    finally:
        sesion = sesiones_activas.get(sid)
        if sesion:
            sesion["captura_en_curso"] = False


def _ejecutar_captura_interno(sid, dni, id_sesion, numero_intento, pef_teorico):
    cola = lector.iniciar_sesion()
    detener_evento = sesiones_activas[sid]["detener"]

    offset = lector.offset_cero
    rho = processing.calcular_densidad_aire()
    filtro = processing.FiltroMediaMovil()

    tiempos, presiones, flujos = [], [], []
    volumen_acum = 0.0
    t_inicio = None
    soplido_iniciado = False
    tiempo_bajo_umbral = None

    try:
        while not detener_evento.is_set():
            try:
                marca_tiempo, presion_cruda = cola.get(timeout=config.SERIAL_TIMEOUT_S)
            except queue.Empty:
                break  # se cortó la fuente de datos

            if t_inicio is None:
                t_inicio = marca_tiempo
            t_rel = marca_tiempo - t_inicio

            presion_corregida = presion_cruda - offset
            presion_filtrada = filtro.filtrar(presion_corregida)
            flujo_l_s = processing.presion_a_flujo(presion_filtrada, rho)
            volumen_acum += flujo_l_s * config.SAMPLE_INTERVAL_S

            tiempos.append(t_rel)
            presiones.append(presion_corregida)
            flujos.append(flujo_l_s)

            socketio.emit(
                "punto_en_vivo",
                {"tiempo": t_rel, "flujo": flujo_l_s, "volumen": volumen_acum},
                to=sid,
            )

            if flujo_l_s >= config.UMBRAL_INICIO_SOPLIDO_L_S:
                soplido_iniciado = True
                tiempo_bajo_umbral = None
            elif soplido_iniciado and flujo_l_s < config.UMBRAL_FIN_SOPLIDO_L_S:
                if tiempo_bajo_umbral is None:
                    tiempo_bajo_umbral = t_rel
                elif t_rel - tiempo_bajo_umbral >= config.UMBRAL_FIN_SOPLIDO_S:
                    break

            if t_rel >= config.DURACION_MAX_PRUEBA_S:
                break
    finally:
        lector.detener_sesion(cola)

    if not soplido_iniciado:
        logger.warning("Intento %d (sesión %s): sin soplido detectado", numero_intento, id_sesion)
        socketio.emit("prueba_error", {"mensaje": "No se detectó ningún soplido durante la prueba."}, to=sid)
        return

    # Reprocesamiento final: filtro por lote sobre la señal completa, volumen
    # integrado con dt fijo del muestreo, y corrección BTPS.
    presion_suave = processing.suavizar_senal(np.array(presiones))
    flujo_final = np.array([processing.presion_a_flujo(p, rho) for p in presion_suave])
    volumen_final = processing.integrar_volumen(flujo_final, config.SAMPLE_INTERVAL_S)
    volumen_final = processing.aplicar_btps(volumen_final)
    tiempo_uniforme = np.arange(len(flujo_final)) * config.SAMPLE_INTERVAL_S

    try:
        metricas = spirometry.calcular_metricas(tiempo_uniforme, flujo_final, volumen_final, pef_teorico)
    except ValueError as error:
        logger.warning("Intento %d (sesión %s): error al calcular métricas: %s", numero_intento, id_sesion, error)
        socketio.emit("prueba_error", {"mensaje": str(error)}, to=sid)
        return

    intento = dict(metricas)
    intento["numero"] = numero_intento
    intento["fecha"] = datetime.now().isoformat(timespec="seconds")
    intento["perfil_simulado"] = config.PERFIL_SIMULACION if config.MODO_SIMULADO else None

    registro = patients.agregar_intento(dni, id_sesion, intento)
    sesion_guardada = next(s for s in registro["sesiones"] if s["id_sesion"] == id_sesion)

    logger.info(
        "Intento %d (sesión %s, paciente %s) completo: PEF=%.2f FVC=%.2f aceptable=%s",
        numero_intento, id_sesion, dni, metricas["pef_real"], metricas["fvc"], metricas["aceptable"],
    )
    socketio.emit(
        "intento_completo",
        {"numero_intento": numero_intento, "sesion": sesion_guardada},
        to=sid,
    )


@socketio.on("iniciar_sesion")
def manejar_iniciar_sesion():
    dni_activo = session.get("paciente_dni")
    paciente = patients.cargar_paciente(dni_activo) if dni_activo else None
    if paciente is None:
        socketio.emit("prueba_error", {"mensaje": "No hay un paciente activo seleccionado."}, to=request.sid)
        return

    pef_teorico = spirometry.calcular_pef_teorico(paciente["sexo"], paciente["edad"], paciente["estatura"])
    id_sesion = patients.crear_sesion(dni_activo, pef_teorico)
    sesiones_activas[request.sid] = {
        "detener": threading.Event(),
        "id_sesion": id_sesion,
        "siguiente_numero_intento": 1,
    }
    logger.info("Sesión %s iniciada para paciente %s (PEF teórico=%.2f)", id_sesion, dni_activo, pef_teorico)
    socketio.emit(
        "sesion_iniciada",
        {"id_sesion": id_sesion, "pef_teorico": pef_teorico, "max_intentos": config.MAX_INTENTOS_POR_SESION},
        to=request.sid,
    )


@socketio.on("iniciar_intento")
def manejar_iniciar_intento():
    dni_activo = session.get("paciente_dni")
    paciente = patients.cargar_paciente(dni_activo) if dni_activo else None
    sesion = sesiones_activas.get(request.sid)
    if paciente is None or sesion is None or "id_sesion" not in sesion:
        socketio.emit("prueba_error", {"mensaje": "No hay una sesión de espirometría activa."}, to=request.sid)
        return

    if sesion["siguiente_numero_intento"] > config.MAX_INTENTOS_POR_SESION:
        socketio.emit(
            "prueba_error",
            {"mensaje": f"Se alcanzó el máximo de {config.MAX_INTENTOS_POR_SESION} intentos por sesión."},
            to=request.sid,
        )
        return

    if sesion.get("captura_en_curso"):
        socketio.emit("prueba_error", {"mensaje": "Ya hay una captura en curso."}, to=request.sid)
        return

    pef_teorico = spirometry.calcular_pef_teorico(paciente["sexo"], paciente["edad"], paciente["estatura"])
    numero_intento = sesion["siguiente_numero_intento"]
    sesion["siguiente_numero_intento"] += 1
    sesion["detener"] = threading.Event()
    sesion["captura_en_curso"] = True

    socketio.start_background_task(
        ejecutar_captura, request.sid, dni_activo, sesion["id_sesion"], numero_intento, pef_teorico
    )


@socketio.on("finalizar_sesion")
def manejar_finalizar_sesion():
    sesion = sesiones_activas.pop(request.sid, None)
    if sesion:
        logger.info("Sesión %s finalizada por el operador", sesion["id_sesion"])


@socketio.on("detener_prueba")
def manejar_detener_prueba():
    sesion = sesiones_activas.get(request.sid)
    if sesion:
        sesion["detener"].set()


@socketio.on("disconnect")
def manejar_desconexion():
    sesion = sesiones_activas.get(request.sid)
    if sesion:
        sesion["detener"].set()


def _parsear_argumentos():
    parser = argparse.ArgumentParser(description="Servidor del espirómetro digital.")
    parser.add_argument(
        "--test",
        nargs="?",
        const="sano",
        choices=["sano", "copd"],
        default=None,
        metavar="PERFIL",
        help="Ejecuta sin hardware con datos sintéticos. PERFIL: sano (default) o copd.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    configurar_logging()
    args = _parsear_argumentos()
    if args.test is not None:
        config.MODO_SIMULADO = True
        config.PERFIL_SIMULACION = args.test

    lector.iniciar()
    socketio.run(app, host="127.0.0.1", port=5000, debug=True, use_reloader=False)
