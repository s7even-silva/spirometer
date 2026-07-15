# SpiroIntelli Pro

Espirómetro digital de bajo costo: servidor web local (Flask + Socket.IO) que
captura la maniobra de espiración forzada de un paciente desde un sensor de
presión diferencial vía puerto serial, calcula las métricas clínicas
estándar (PEF, FVC, FEV1, FEV1/FVC, FEF25-75%) y las compara contra valores
de referencia.

## Funcionalidad

- **Historial clínico**: registro de pacientes (DNI, edad, sexo, estatura,
  tabaquismo) persistido en SQLite (`espirometro.db`), con una vista por
  paciente (`/historial/<dni>`) que lista todas sus sesiones pasadas y el
  detalle de cada intento.
- **Registro con fecha/hora manual**: al iniciar una sesión se puede fijar
  una fecha distinta a la actual (por ejemplo, para digitalizar una prueba
  hecha en papel); nunca sobrescribe sesiones existentes, cada una queda
  como un registro independiente.
- **Sesión de espirometría con múltiples intentos**: cada sesión admite
  hasta 8 maniobras; se reporta el mejor PEF y el mejor FVC/FEV1 (no
  necesariamente del mismo intento), siguiendo el criterio clínico
  ATS/ERS.
- **Criterios de aceptabilidad automáticos**: duración mínima, meseta de
  fin de espiración, ausencia de interrupciones/tos, arranque explosivo y
  extrapolación retroactiva (back-extrapolation) para fijar t₀ con
  precisión.
- **Repetibilidad entre intentos**: diferencia de FVC entre los dos
  mejores intentos de la sesión.
- **Corrección física de la señal**: conversión presión → flujo con
  modelo de tubo Venturi/Pitot, densidad del aire por temperatura/presión/
  humedad, corrección BTPS del volumen exhalado.
- **Detección automática de altitud** por geolocalización de IP (con
  ajuste manual desde la interfaz) para corregir la densidad del aire sin
  depender de un valor fijo de fábrica.
- **Modo de simulación** (`--test`) para desarrollar y probar sin hardware
  conectado, con perfiles sintéticos de paciente sano y de patrón
  obstructivo (COPD).
- **Detección y predicción de riesgo de EPOC por IA** (modelo DeepSpiro,
  ver más abajo): para cada intento aceptable de la sesión, se ejecuta el
  pipeline SpiroEncoder → SpiroExplainer (detección) → SpiroPredictor
  (riesgo a 1-5 años si no se detecta EPOC activo), mostrado en un panel
  dedicado en la vista de resultados.
- Interfaz con modo claro/oscuro y gráficas en vivo (Plotly) de flujo,
  volumen y el lazo flujo-volumen.

## Requisitos

- Python 3.10+
- Un sensor de presión diferencial conectado por puerto serial que envíe
  la lectura en Pascales, una línea por muestra, a la cadencia configurada
  en `config.py` (100 Hz por defecto). Sin hardware, se puede usar el modo
  de simulación.

## Instalación

```bash
python3 -m venv venv
source venv/bin/activate  # en Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

Con el sensor conectado (ajustar `SERIAL_PORT` y `BAUD_RATE` en
`config.py` según el puerto real):

```bash
python app.py
```

Sin hardware, en modo simulación:

```bash
python app.py --test          # perfil sano (por defecto)
python app.py --test copd     # perfil con patrón obstructivo
```

La aplicación queda disponible en `http://127.0.0.1:5000`. El flujo es:
registrar o seleccionar un paciente en **Historial clínico**, luego
**Prueba de espirometría** para capturar la maniobra y ver los resultados.

## Configuración

Todas las constantes físicas y de hardware (geometría del tubo,
condiciones ambientales, umbrales de detección de la maniobra, criterios
de aceptabilidad) están centralizadas en [`config.py`](config.py), con
comentarios explicando cada una. Ninguno de los valores por defecto está
calibrado contra un sensor real: deben ajustarse según el tubo y el sensor
usados.

## Estructura del proyecto

```
app.py              Servidor Flask + orquestación de la sesión vía Socket.IO
config.py           Constantes físicas, de hardware y de criterios clínicos
processing.py       Conversión presión↔flujo, densidad del aire, BTPS, filtros
spirometry.py       Métricas clínicas, aceptabilidad, repetibilidad, diagnóstico
patients.py         Persistencia del historial clínico en SQLite (espirometro.db)
serial_reader.py    Lectura continua del puerto serial (o señal simulada)
perfiles_simulacion.py  Curvas sintéticas de flujo para el modo --test
deepspiro_ia.py     Integración con el modelo DeepSpiro (detección/predicción EPOC)
altitud.py          Estimación de presión atmosférica por geolocalización IP
logging_config.py   Configuración de logs (consola + archivo rotativo)
templates/          Vistas Jinja (historial, prueba, layout base)
static/             CSS, JS del cliente e imágenes
COPD-Early-Prediction/  Modelo DeepSpiro de terceros (pesos + código vendido)
```

## Base de datos

El historial clínico vive en un único archivo SQLite (`espirometro.db`),
creado automáticamente al arrancar la aplicación. Se puede inspeccionar sin
correr la web con cualquier cliente SQLite estándar:

```bash
sqlite3 espirometro.db "SELECT dni, nombre FROM pacientes;"
```

o con una herramienta gráfica como [DB Browser for SQLite](https://sqlitebrowser.org/)
o la extensión "SQLite Viewer" de VS Code.

## IA de detección y predicción de EPOC (DeepSpiro)

El directorio `COPD-Early-Prediction/` contiene el código y los pesos de
DeepSpiro (Mei et al., *"[Deep Learning for Detecting and Early
Predicting Chronic Obstructive Pulmonary Disease from Spirogram Time
Series](https://doi.org/10.1038/s41540-025-00489-y)"*, 2025), usado sin
modificaciones en su lógica de modelado. `deepspiro_ia.py` es el
adaptador que mapea la curva ya calculada por nuestro propio pipeline
(`spirometry.calcular_metricas`) al formato de entrada que ese modelo
espera, y llama directamente a sus funciones de preprocesamiento e
inferencia originales (`process_data`, `run_spiro_encoder`,
`run_spiro_explainer`, `run_spiro_predictor`). No se reentrenó ni se
ajustaron (fine-tuning) los pesos: el modelo se usa tal cual viene
pre-entrenado.

El único cambio a código de terceros es una corrección de un bug real en
`COPD-Early-Prediction/utils/predict_utils.py` (`preprocess_data`): la
rama de carga de archivos `.xlsx` estaba rota (el procesamiento estaba
anidado solo bajo la rama `.csv`), lo que hacía que cargar el propio
ejemplo `.xlsx` de su documentación devolviera `None`.

Los modelos se cargan una sola vez al arrancar el servidor (en un hilo
aparte, sin bloquear el arranque) y detectan automáticamente si hay GPU
disponible (CUDA), usando CPU si no la hay. Si los pesos o las
dependencias no están disponibles, la predicción por IA queda
deshabilitada sin afectar el resto de la aplicación.

**Solo se ejecuta sobre intentos aceptables** (misma validación ATS/ERS
que ya usa la app): un intento descartado por nuestros propios criterios
de calidad no es una entrada confiable para el modelo tampoco.

**Importante**: en modo de simulación (`--test`), el panel de IA muestra
un aviso explícito de que el resultado no es representativo de un caso
real. Los perfiles sintéticos (`perfiles_simulacion.py`) están ajustados
para ser fisiológicamente plausibles (FVC dentro del rango de
entrenamiento del modelo), pero siguen siendo curvas generadas por una
fórmula matemática, no de un pulmón real — el modelo puede dar una
predicción con aparente confianza sobre ellas sin que eso tenga validez
clínica. Ese aviso solo debe aparecer con `--test`; con datos de un
paciente real (hardware conectado) no se muestra.

## Notas

- `Historiales_Medicos/`, `logs/`, `venv/` y `espirometro.db` están
  excluidos del control de versiones (ver `.gitignore`); son datos/
  artefactos locales.
- La interfaz está diseñada para escritorio; no es responsiva.
