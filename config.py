"""
Configuración física y de hardware del espirómetro.

Todas las constantes usadas para convertir la diferencia de presión (Pa)
leída por el puerto serial en flujo (L/s) y volumen (L) están aquí.
Edita estos valores según el sensor, el tubo y el entorno reales:
ninguno de estos números está calibrado, son valores de ejemplo.
"""

# =====================================================================
# Comunicación serial
# =====================================================================
SERIAL_PORT = "COM20"
BAUD_RATE = 115200
SAMPLE_INTERVAL_S = 0.010          # 10 ms => 100 Hz, cadencia de envío del microcontrolador
SERIAL_TIMEOUT_S = 1.0
RECONEXION_ESPERA_S = 2.0          # segundos entre reintentos si el puerto se desconecta
PUERTO_SIN_DATOS_TIMEOUT_S = 0.5   # sin muestras nuevas por más de esto, se considera "sin datos" en la UI

# Si no hay hardware conectado, genera una señal sintética de soplido en vez
# de abrir el puerto real. Útil para desarrollar y probar la UI sin sensor.
MODO_SIMULADO = False

# Perfil clínico usado por la señal sintética cuando MODO_SIMULADO está activo
# ("sano" o "copd"; ver perfiles_simulacion.py). Se puede fijar al arrancar con
# `python app.py --test copd`, lo que sobreescribe este valor en tiempo de ejecución.
PERFIL_SIMULACION = "sano"

# =====================================================================
# Geometría del tubo de flujo (tipo Venturi / Pitot con restricción)
# =====================================================================
# D1: diámetro de la sección amplia (entrada), D2: diámetro de la garganta/orificio.
DIAMETRO_ENTRADA_MM = 10
DIAMETRO_GARGANTA_MM = 5
COEFICIENTE_DESCARGA_CD = 0.98      # Cd típico 0.95-0.99, se ajusta con calibración empírica

# =====================================================================
# Condiciones ambientales / densidad del aire
# =====================================================================
TEMPERATURA_AMBIENTE_C = 22.0
PRESION_ATMOSFERICA_KPA = 101.325
HUMEDAD_RELATIVA_PCT = 50.0

# Si se fija un valor aquí (distinto de None), se usa directamente y se
# ignoran temperatura/presión/humedad de arriba para calcular la densidad.
DENSIDAD_AIRE_MANUAL_KG_M3 = None

# =====================================================================
# Corrección BTPS (Body Temperature, Pressure, Saturated)
# =====================================================================
# El volumen se mide en condiciones ambiente (ATPS) y se corrige a las
# condiciones dentro del cuerpo (BTPS) como exige la espirometría clínica.
APLICAR_BTPS = True
BTPS_TEMP_CORPORAL_C = 37.0

# =====================================================================
# Calibración de cero y filtrado de señal
# =====================================================================
MUESTRAS_CALIBRACION_CERO = 50        # nº de muestras en reposo para el offset de presión
VENTANA_FILTRO_MEDIA_MOVIL = 5        # nº de muestras para suavizar la señal de presión (filtro en vivo, muestra a muestra)

# Filtro pasa-bajos Butterworth (orden 2, fase cero vía filtfilt) aplicado en
# el reprocesamiento offline sobre la señal de presión completa, antes de
# convertir a flujo. Elimina jitter de alta frecuencia del sensor/ADC de forma
# más agresiva que la media móvil, sin el retraso ni el aplanamiento del pico
# (PEF) que introduciría una media móvil con una ventana igual de efectiva.
FILTRO_BUTTERWORTH_ORDEN = 2
FILTRO_BUTTERWORTH_CORTE_HZ = 10.0     # frecuencia de corte; la dinámica real de un soplido está muy por debajo

# =====================================================================
# Detección de inicio/fin de la maniobra espirométrica
# =====================================================================
UMBRAL_INICIO_SOPLIDO_L_S = 0.15      # flujo mínimo para considerar que empezó el soplido
UMBRAL_FIN_SOPLIDO_L_S = 0.05         # flujo por debajo del cual se considera que terminó
UMBRAL_FIN_SOPLIDO_S = 1.0            # segundos sostenidos bajo el umbral para dar la prueba por finalizada

# Corte de seguridad por duración si el flujo nunca baja del umbral de fin de
# soplido. El operador puede fijar este valor por intento desde la UI (dentro
# de [DURACION_INTENTO_MIN_S, DURACION_INTENTO_MAX_S]); este es solo el valor
# por defecto que se precarga en el formulario.
DURACION_MAX_PRUEBA_S = 15.0
DURACION_INTENTO_MIN_S = 3.0
DURACION_INTENTO_MAX_S = 60.0

# =====================================================================
# Sesión de espirometría (múltiples intentos, estándar ATS/ERS simplificado)
# =====================================================================
MAX_INTENTOS_POR_SESION = 8

# Criterios de aceptabilidad de cada intento (heurística ATS/ERS simplificada).
FET_MINIMO_ACEPTABLE_S = 3.0           # duración mínima de la espiración activa
VENTANA_MESETA_S = 0.5                 # ventana final para verificar meseta de volumen
TOLERANCIA_MESETA_VOLUMEN_L = 0.025    # cambio máximo de volumen admitido en esa ventana
TIEMPO_MAXIMO_PEF_ACEPTABLE_S = 0.5    # el pico debe alcanzarse rápido (esfuerzo explosivo)
FLUJO_MINIMO_INTERRUPCION_L_S = -1.0   # flujo por debajo de esto sugiere tos/interrupción

# Extrapolación retroactiva (back-extrapolation) para fijar t0 con precisión:
# el volumen extrapolado (Vbe) debe ser menor al mayor entre estos dos límites.
EXTRAPOLACION_MAX_PCT_FVC = 0.05       # 5% del FVC
EXTRAPOLACION_MAX_ABSOLUTA_L = 0.150   # 150 mL

# Repetibilidad entre intentos: diferencia máxima admitida entre los dos
# mejores FVC de una sesión para considerarla clínicamente repetible.
REPETIBILIDAD_MAX_DIFERENCIA_FVC_L = 0.150
