"""
Lectura continua e ininterrumpida del puerto serial (o de una señal
simulada) donde llega la diferencia de presión cruda (Pa) cada 10ms.

Corre en un hilo de fondo desde que arranca la aplicación, sin depender
de que haya una prueba de espirometría en curso. Mientras no hay ninguna
sesión de captura activa, mantiene actualizado un offset de calibración
de cero (promedio de la señal en reposo) para compensar deriva del sensor.
"""
import logging
import queue
import threading
import time
from collections import deque

import numpy as np
import serial

import config
import perfiles_simulacion
import processing

logger = logging.getLogger(__name__)


class LectorSerial:
    def __init__(self):
        self._lock = threading.Lock()
        self._suscriptores = []  # colas activas, una por sesión de captura en curso
        self._calibracion = deque(maxlen=config.MUESTRAS_CALIBRACION_CERO)
        self.offset_cero = 0.0
        self._hilo = None
        self._detener = threading.Event()
        # Estado de conexión expuesto a la UI: "conectado" refleja si el puerto
        # serial está abierto ahora mismo (o si estamos en modo simulado), y
        # "ultima_muestra_ts" permite distinguir un puerto abierto pero mudo
        # (cable sin sensor, firmware equivocado) de uno que sí está enviando
        # datos válidos.
        self.conectado = False
        self.ultima_muestra_ts = None

    # ------------------------------------------------------------------
    # Ciclo de vida del hilo
    # ------------------------------------------------------------------
    def iniciar(self):
        if self._hilo and self._hilo.is_alive():
            return
        self._detener.clear()
        self._hilo = threading.Thread(target=self._bucle_lectura, daemon=True)
        self._hilo.start()
        modo = f"simulado ({config.PERFIL_SIMULACION})" if config.MODO_SIMULADO else "hardware"
        logger.info("LectorSerial iniciado en modo %s", modo)

    def detener(self):
        self._detener.set()
        logger.info("LectorSerial detenido")

    def reiniciar(self):
        """Detiene el hilo de lectura actual y arranca uno nuevo, para que un
        cambio de config.SERIAL_PORT (o de MODO_SIMULADO) tome efecto sin
        reiniciar el proceso completo. Las sesiones de captura suscritas
        siguen registradas: si el nuevo puerto no llega a abrirse, simplemente
        no reciben muestras hasta que se reintente la conexión."""
        self._detener.set()
        if self._hilo:
            self._hilo.join(timeout=config.SERIAL_TIMEOUT_S + 1.0)
        self.conectado = False
        self.ultima_muestra_ts = None
        self.iniciar()

    def _bucle_lectura(self):
        if config.MODO_SIMULADO:
            self._bucle_simulado()
        else:
            self._bucle_hardware()

    # ------------------------------------------------------------------
    # Hardware real: abre el puerto y se reconecta solo si se cae
    # ------------------------------------------------------------------
    def _bucle_hardware(self):
        while not self._detener.is_set():
            try:
                with serial.Serial(
                    config.SERIAL_PORT, config.BAUD_RATE, timeout=config.SERIAL_TIMEOUT_S
                ) as puerto:
                    puerto.reset_input_buffer()
                    logger.info("Puerto serial %s abierto (%d baud)", config.SERIAL_PORT, config.BAUD_RATE)
                    self.conectado = True
                    while not self._detener.is_set():
                        linea = puerto.readline().decode("utf-8", errors="ignore").strip()
                        if not linea:
                            continue
                        try:
                            presion_pa = float(linea)
                        except ValueError:
                            logger.warning("Línea serial no numérica descartada: %r", linea)
                            continue
                        self._procesar_muestra(presion_pa)
            except serial.SerialException as error:
                self.conectado = False
                logger.warning(
                    "Puerto serial %s no disponible (%s), reintentando en %.1fs",
                    config.SERIAL_PORT, error, config.RECONEXION_ESPERA_S,
                )
                time.sleep(config.RECONEXION_ESPERA_S)
        self.conectado = False

    # ------------------------------------------------------------------
    # Modo simulado: sin hardware conectado, genera un soplido sintético
    # cuando se abre una sesión de captura (para probar todo el pipeline y la UI)
    # ------------------------------------------------------------------
    def _bucle_simulado(self):
        """Genera como máximo un soplido sintético por sesión de captura suscrita
        (una llamada a iniciar_sesion): al terminar, se queda en reposo hasta que
        esa cola se cierre y una nueva sesión (nuevo intento) se suscriba."""
        rho = processing.calcular_densidad_aire()
        t = 0.0
        t_inicio_soplido = None
        habia_suscriptor = False
        soplido_emitido = False
        self.conectado = True

        while not self._detener.is_set():
            hay_suscriptor = len(self._suscriptores) > 0
            if hay_suscriptor and not habia_suscriptor:
                soplido_emitido = False
            habia_suscriptor = hay_suscriptor

            perfil = config.PERFIL_SIMULACION
            duracion_soplido = perfiles_simulacion.PERFILES[perfil]["duracion_s"]

            if t_inicio_soplido is None and hay_suscriptor and not soplido_emitido:
                t_inicio_soplido = t

            if t_inicio_soplido is not None and (t - t_inicio_soplido) < duracion_soplido:
                t_relativo = t - t_inicio_soplido
                flujo_l_s = perfiles_simulacion.flujo_objetivo_l_s(perfil, t_relativo)
                presion_pa = processing.flujo_a_presion(flujo_l_s, rho)
            else:
                if t_inicio_soplido is not None:
                    soplido_emitido = True
                t_inicio_soplido = None
                presion_pa = float(np.random.normal(0, 0.5))  # ruido de reposo

            self._procesar_muestra(presion_pa)
            t += config.SAMPLE_INTERVAL_S
            time.sleep(config.SAMPLE_INTERVAL_S)

    # ------------------------------------------------------------------
    # Distribución de cada muestra a las sesiones activas + calibración de cero
    # ------------------------------------------------------------------
    def _procesar_muestra(self, presion_pa):
        marca_tiempo = time.time()
        muestra = (marca_tiempo, presion_pa)
        self.ultima_muestra_ts = marca_tiempo
        with self._lock:
            if not self._suscriptores:
                self._calibracion.append(presion_pa)
                self.offset_cero = sum(self._calibracion) / len(self._calibracion)
            for cola in self._suscriptores:
                cola.put(muestra)

    def iniciar_sesion(self):
        """Registra una nueva sesión de captura y devuelve la cola por la que recibirá muestras."""
        cola = queue.Queue()
        with self._lock:
            self._suscriptores.append(cola)
        logger.info("Sesión de captura suscrita (offset_cero=%.3f Pa)", self.offset_cero)
        return cola

    def detener_sesion(self, cola):
        with self._lock:
            if cola in self._suscriptores:
                self._suscriptores.remove(cola)
        logger.info("Sesión de captura finalizada")

    def recibiendo_datos(self):
        """True solo si el puerto está abierto y llegó una muestra hace poco:
        un puerto conectado pero mudo (sensor mal cableado, firmware
        equivocado) debe distinguirse de uno que sí está transmitiendo."""
        if not self.conectado or self.ultima_muestra_ts is None:
            return False
        return (time.time() - self.ultima_muestra_ts) < config.PUERTO_SIN_DATOS_TIMEOUT_S


lector = LectorSerial()
