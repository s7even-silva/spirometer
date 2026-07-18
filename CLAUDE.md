# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SpiroIntelli Pro: a local web server (Flask + Socket.IO) for a low-cost
digital spirometer. It captures a forced-expiration maneuver from a
differential pressure sensor over serial, computes standard clinical
metrics (PEF, FVC, FEV1, FEV1/FVC, FEF25-75%), compares them against
predicted reference values, and optionally runs a third-party COPD
detection/risk model (DeepSpiro) on each acceptable attempt. All code
comments, docstrings, and identifiers in this repo are in Spanish —
match that convention when editing.

## Running

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py                 # expects real hardware on config.SERIAL_PORT
python app.py --test          # simulated signal, healthy profile
python app.py --test copd     # simulated signal, obstructive/COPD profile
```

Serves at `http://127.0.0.1:5000`. There is no test suite, linter, or
build step configured in this repo — verify changes by running the app
(use `--test` mode when no sensor is attached) and exercising the
affected flow in the browser.

Inspect the SQLite database directly without running the app:
```bash
sqlite3 espirometro.db "SELECT dni, nombre FROM pacientes;"
```

## Architecture

**Data flow**: `serial_reader.lector` runs as a background thread from
process start, continuously reading raw pressure samples (Pa) from serial
(or, in `--test` mode, from a synthetic signal in `perfiles_simulacion.py`,
converted to a fake pressure via `processing.flujo_a_presion`). It
broadcasts samples to any subscribed capture session queue and, when no
session is active, keeps a rolling zero-offset calibration.

When the operator starts an attempt, `app.py`'s `ejecutar_captura`
subscribes a queue, and for every sample: subtracts the zero offset,
smooths it (`processing.FiltroMediaMovil`), converts pressure→flow via a
Venturi/Pitot tube model (`processing.presion_a_flujo`), integrates flow
into volume, and streams live points to the browser over Socket.IO
(`punto_en_vivo`). It also runs simple threshold logic to detect
blow-start/blow-end and stop the capture loop.

Once capture ends, there's a **second, more careful offline pass**: the
full pressure buffer is smoothed and reconverted (`processing.suavizar_senal`
+ `presion_a_flujo`), volume is re-integrated with a fixed dt and BTPS-
corrected (`processing.aplicar_btps`), then handed to
`spirometry.calcular_metricas`, which:
- finds t0 precisely via ATS/ERS back-extrapolation (`back_extrapolar_t0`),
  trimming the curve so FVC/FEV1 start from volume 0
- computes PEF, FVC, FEV1, FEV1/FVC%, FEF25-75%, FET
- runs ATS/ERS acceptability checks (`evaluar_aceptabilidad`): duration,
  end-of-expiration plateau, no cough/interruption, explosive start,
  back-extrapolation volume limit

If the attempt is acceptable, `deepspiro_ia.predecir` runs the DeepSpiro
pipeline (SpiroEncoder → SpiroExplainer → SpiroPredictor); otherwise the
attempt is stored with `ia.disponible = False` — quality-rejected curves
are never fed to the model. The finished attempt is persisted via
`patients.agregar_intento`, which also recomputes the session summary
(`spirometry.resumir_sesion` — best PEF and best FVC/FEV1 may come from
*different* attempts, per clinical convention, plus repeatability between
the two best FVC values) and pushes `intento_completo` back to the client.

**Session/attempt hierarchy**: paciente → sesión (one clinical visit,
`id_sesion` is its timestamp, or timestamp+suffix on collision) → up to
`MAX_INTENTOS_POR_SESION` intentos (maneuvers). Sessions can be created
with a manual past `fecha` (for digitizing paper results) without
overwriting existing sessions. All of this lives in `espirometro.db`
(SQLite): `pacientes`/`sesiones` have queryable columns, but full curves
and per-attempt detail are serialized as JSON in `datos_json`/
`resumen_json` columns (see `patients.py` module docstring for the
rationale).

**Config is centralized** in `config.py` — tube geometry, ambient
conditions/air density, BTPS correction, zero-calibration/filter window,
blow start/end thresholds, acceptability and repeatability criteria, and
serial port/simulation mode. Several of these are mutated at runtime (not
just read): `app.py` routes `/config/altitud` and `/config/puerto_serial`
write directly to `config.PRESION_ATMOSFERICA_KPA` / `config.SERIAL_PORT`
/ `config.MODO_SIMULADO`, and changing the serial port calls
`lector.reiniciar()` to restart the background thread live. None of the
default physical constants are calibrated against a real sensor.

**DeepSpiro integration** (`deepspiro_ia.py` + `COPD-Early-Prediction/`):
third-party pretrained model (Mei et al. 2025), vendored as-is and used
unmodified except one real bug fix in
`COPD-Early-Prediction/utils/predict_utils.py` (`preprocess_data`'s
`.xlsx` branch was nested incorrectly under `.csv`). `deepspiro_ia.py` is
purely an adapter: it reformats our already-computed curve
(`spirometry.calcular_metricas` output) into the row format DeepSpiro's
own `process_data`/`run_spiro_encoder`/`run_spiro_explainer`/
`run_spiro_predictor` expect — no reimplementation of its modeling logic.
Models load lazily/once in a background thread at startup
(`app.py` calls `deepspiro_ia._cargar_modelos` in a daemon thread); if
weights or deps are missing, AI prediction is silently disabled without
affecting the rest of the app (`predecir` never raises to its caller). In
`--test` mode the UI must show a disclaimer that predictions on synthetic
curves aren't clinically meaningful — see `perfiles_simulacion.py`
docstring for why the COPD profile needed a bi-exponential shape (a
simpler decay gave clinically unrealistic FVC > 10L).

**Altitude detection** (`altitud.py`): best-effort IP geolocation +
barometric formula to suggest atmospheric pressure at startup, run in a
background thread so missing internet never blocks server start. Always
overridable from the UI; manual correction takes precedence.

## Key files

| File | Responsibility |
|---|---|
| `app.py` | Flask routes + Socket.IO event handlers; orchestrates the live capture loop |
| `config.py` | All physical/hardware/clinical-threshold constants, some mutated at runtime |
| `processing.py` | Pressure↔flow physics, air density, BTPS, signal filtering |
| `spirometry.py` | Clinical metrics, acceptability, repeatability, session summary |
| `patients.py` | SQLite persistence for patients/sessions/attempts |
| `serial_reader.py` | Background thread reading serial or simulated signal |
| `perfiles_simulacion.py` | Synthetic flow curves for `--test` mode |
| `deepspiro_ia.py` | Adapter into the vendored DeepSpiro COPD model |
| `altitud.py` | IP-based atmospheric pressure estimation |
| `COPD-Early-Prediction/` | Vendored third-party model code + weights — avoid modifying beyond the one documented bug fix |
