"""
Lectura continua e ininterrumpida del puerto serial (o de una señal
simulada) donde llega la diferencia de presión cruda (Pa) cada 10ms.

Corre en un hilo de fondo desde que arranca la aplicación, sin depender
de que haya una prueba de espirometría en curso. Mientras no hay ninguna
sesión de captura activa, mantiene actualizado un offset de calibración
de cero (promedio de la señal en reposo) para compensar deriva del sensor.
"""
import math
import queue
import threading
import time
from collections import deque

import numpy as np
import serial

import config
import processing


class LectorSerial:
    def __init__(self):
        self._lock = threading.Lock()
        self._suscriptores = []  # colas activas, una por sesión de captura en curso
        self._calibracion = deque(maxlen=config.MUESTRAS_CALIBRACION_CERO)
        self.offset_cero = 0.0
        self._hilo = None
        self._detener = threading.Event()

    # ------------------------------------------------------------------
    # Ciclo de vida del hilo
    # ------------------------------------------------------------------
    def iniciar(self):
        if self._hilo and self._hilo.is_alive():
            return
        self._detener.clear()
        self._hilo = threading.Thread(target=self._bucle_lectura, daemon=True)
        self._hilo.start()

    def detener(self):
        self._detener.set()

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
                    while not self._detener.is_set():
                        linea = puerto.readline().decode("utf-8", errors="ignore").strip()
                        if not linea:
                            continue
                        try:
                            presion_pa = float(linea)
                        except ValueError:
                            continue
                        self._procesar_muestra(presion_pa)
            except serial.SerialException:
                time.sleep(config.RECONEXION_ESPERA_S)

    # ------------------------------------------------------------------
    # Modo simulado: sin hardware conectado, genera un soplido sintético
    # cuando se abre una sesión de captura (para probar todo el pipeline y la UI)
    # ------------------------------------------------------------------
    def _bucle_simulado(self):
        rho = processing.calcular_densidad_aire()
        t = 0.0
        t_inicio_soplido = None

        while not self._detener.is_set():
            if t_inicio_soplido is None and len(self._suscriptores) > 0:
                t_inicio_soplido = t

            if t_inicio_soplido is not None and (t - t_inicio_soplido) < 6.0:
                t_relativo = t - t_inicio_soplido
                flujo_l_s = 7.8 * (t_relativo / 0.3) * math.exp(1 - t_relativo / 0.3)
                presion_pa = processing.flujo_a_presion(flujo_l_s, rho)
            else:
                t_inicio_soplido = None
                presion_pa = float(np.random.normal(0, 0.5))  # ruido de reposo

            self._procesar_muestra(presion_pa)
            t += config.SAMPLE_INTERVAL_S
            time.sleep(config.SAMPLE_INTERVAL_S)

    # ------------------------------------------------------------------
    # Distribución de cada muestra a las sesiones activas + calibración de cero
    # ------------------------------------------------------------------
    def _procesar_muestra(self, presion_pa):
        muestra = (time.time(), presion_pa)
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
        return cola

    def detener_sesion(self, cola):
        with self._lock:
            if cola in self._suscriptores:
                self._suscriptores.remove(cola)


lector = LectorSerial()
