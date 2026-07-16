const socket = io();

const graficaVivoDiv = document.getElementById("grafica-vivo");
const btnIniciarSesion = document.getElementById("btn-iniciar-sesion");
const btnNuevoIntento = document.getElementById("btn-nuevo-intento");
const btnDetener = document.getElementById("btn-detener");
const btnFinalizarSesion = document.getElementById("btn-finalizar-sesion");
const contadorIntentos = document.getElementById("contador-intentos");
const estadoCaptura = document.getElementById("estado-captura");
const tarjetaIntentos = document.getElementById("tarjeta-intentos");
const listaIntentos = document.getElementById("lista-intentos");

// --- Selección de puerto serial ---
const puertoSerialSelect = document.getElementById("puerto-serial-select");
const btnRefrescarPuertos = document.getElementById("btn-refrescar-puertos");
const btnConectarPuerto = document.getElementById("btn-conectar-puerto");
const puertoSerialEstado = document.getElementById("puerto-serial-estado");
const URL_PUERTO_SERIAL = "/config/puerto_serial";

function pintarEstadoPuerto(data) {
    const opcionesActuales = Array.from(puertoSerialSelect.options).map((o) => o.value);
    const puertos = data.puertos_disponibles || [];
    if (opcionesActuales.join(",") !== puertos.join(",")) {
        puertoSerialSelect.innerHTML = "";
        if (puertos.length === 0) {
            puertoSerialSelect.appendChild(new Option("Sin puertos detectados", ""));
        } else {
            puertos.forEach((p) => puertoSerialSelect.appendChild(new Option(p, p)));
        }
    }
    if (puertos.includes(data.puerto_actual)) {
        puertoSerialSelect.value = data.puerto_actual;
    }
    puertoSerialEstado.textContent = data.modo_simulado
        ? "Modo simulación activo"
        : `Conectado a ${data.puerto_actual}`;
}

function cargarPuertosSeriales() {
    fetch(URL_PUERTO_SERIAL)
        .then((r) => r.json())
        .then(pintarEstadoPuerto)
        .catch(() => { puertoSerialEstado.textContent = "No se pudo consultar el puerto serial."; });
}

btnRefrescarPuertos.addEventListener("click", cargarPuertosSeriales);

btnConectarPuerto.addEventListener("click", () => {
    const puerto = puertoSerialSelect.value;
    if (!puerto) return;
    btnConectarPuerto.disabled = true;
    puertoSerialEstado.textContent = "Conectando...";
    const cuerpo = new FormData();
    cuerpo.append("puerto", puerto);
    fetch(URL_PUERTO_SERIAL, { method: "POST", body: cuerpo })
        .then((r) => r.json())
        .then((data) => {
            pintarEstadoPuerto(data);
            btnConectarPuerto.disabled = false;
        })
        .catch(() => {
            puertoSerialEstado.textContent = "No se pudo cambiar el puerto serial.";
            btnConectarPuerto.disabled = false;
        });
});

cargarPuertosSeriales();

// --- Navegación entre la vista de medición y la de resultados (paso 2 / 3) ---
const vistaToggle = document.getElementById("vista-toggle");
const tabResultados = document.getElementById("tab-resultados");
const vistaTabs = document.querySelectorAll(".vista-tab");
const vistaMedicion = document.getElementById("vista-medicion");
const vistaResultados = document.getElementById("vista-resultados");
const stepMedicion = document.querySelector('.step[data-vista-objetivo="medicion"]');
const stepResultados = document.getElementById("step-resultados");

function redimensionarGraficas(contenedorId) {
    document.querySelectorAll(`#${contenedorId} .js-plotly-plot`).forEach((div) => {
        // Plotly.Plots.resize() no siempre recalcula bien un gauge (type:
        // "indicator") tras un cambio de devicePixelRatio (zoom con Ctrl+rueda
        // sin cambiar el tamaño de ventana en px CSS): el número y las
        // etiquetas del arco quedaban con el layout del zoom anterior. Volver
        // a llamar Plotly.react con el layout ya guardado fuerza un relayout
        // completo, que sí recalcula el indicator correctamente.
        if (div.layout) {
            Plotly.react(div, div.data, div.layout, PLOTLY_CONFIG);
        } else {
            Plotly.Plots.resize(div);
        }
    });
}

// ResizeObserver detecta cualquier cambio real de tamaño en píxeles CSS del
// contenedor, incluido el que provoca el zoom del navegador (Ctrl+rueda),
// que no siempre dispara el evento "resize" de window de forma fiable.
const observadorResize = new ResizeObserver((entradas) => {
    for (const entrada of entradas) {
        redimensionarGraficas(entrada.target.id);
    }
});
observadorResize.observe(vistaMedicion);
observadorResize.observe(vistaResultados);

function mostrarVista(nombre) {
    vistaMedicion.hidden = nombre !== "medicion";
    vistaResultados.hidden = nombre !== "resultados";
    vistaTabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.vista === nombre));

    if (stepMedicion) {
        stepMedicion.classList.toggle("active", nombre === "medicion");
        stepMedicion.classList.toggle("done", nombre === "resultados");
    }
    if (stepResultados && !stepResultados.classList.contains("disabled")) {
        stepResultados.classList.toggle("active", nombre === "resultados");
    }

    // Plotly no redimensiona solo al pasar de hidden a visible (el contenedor
    // no dispara resize), así que se fuerza tras el reflow del navegador. El
    // ResizeObserver de arriba cubre cambios posteriores (zoom, etc.).
    const contenedorId = nombre === "medicion" ? "vista-medicion" : "vista-resultados";
    requestAnimationFrame(() => redimensionarGraficas(contenedorId));
}

vistaTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
        if (!tab.disabled) mostrarVista(tab.dataset.vista);
    });
});

function habilitarPasoResultados() {
    vistaToggle.hidden = false;
    tabResultados.disabled = false;
    if (stepResultados) {
        stepResultados.classList.remove("disabled");
        stepResultados.title = "";
    }
}

// Paleta fija para diferenciar cada intento en el overlay flujo-volumen: el
// mejor PEF siempre usa el color de acento del tema, el resto rota entre
// estos colores (elegidos con buen contraste en claro y oscuro) en vez de
// mostrarse todos del mismo gris, que hacía indistinguibles los intentos.
const PALETA_INTENTOS = ["#B4459A", "#D97706", "#7C5CFC", "#0891B2", "#DB2777", "#65A30D"];

function tema() {
    const estilo = getComputedStyle(document.documentElement);
    return {
        accent: estilo.getPropertyValue("--accent").trim(),
        critical: estilo.getPropertyValue("--critical").trim(),
        ink: estilo.getPropertyValue("--ink").trim(),
        inkMuted: estilo.getPropertyValue("--ink-muted").trim(),
        border: estilo.getPropertyValue("--border").trim(),
        surface: estilo.getPropertyValue("--surface").trim(),
        okSoft: estilo.getPropertyValue("--ok-soft").trim(),
        warnSoft: estilo.getPropertyValue("--warn-soft").trim(),
        criticalSoft: estilo.getPropertyValue("--critical-soft").trim(),
    };
}

function layoutBase(t) {
    return {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: t.inkMuted, family: "-apple-system, Segoe UI, sans-serif", size: 12 },
        xaxis: { showgrid: true, gridcolor: t.border, zeroline: false, color: t.inkMuted },
        yaxis: { showgrid: true, gridcolor: t.border, zeroline: false, color: t.inkMuted },
    };
}

function trazaVacia(t) {
    return [{ x: [], y: [], mode: "lines", line: { color: t.accent, width: 2.5 } }];
}

const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };

Plotly.newPlot(graficaVivoDiv, trazaVacia(tema()), {
    ...layoutBase(tema()),
    margin: { l: 44, r: 20, t: 10, b: 40 },
    xaxis: { ...layoutBase(tema()).xaxis, title: "Tiempo (s)" },
    yaxis: { ...layoutBase(tema()).yaxis, title: "Flujo (L/s)" },
}, PLOTLY_CONFIG);

let sesionActual = { idSesion: null, intentos: [], maxIntentos: Infinity };
let ultimoResumen = null;

document.addEventListener("spiro-tema-cambiado", () => {
    if (ultimoResumen) {
        pintarResultados(ultimoResumen.resumen, ultimoResumen.intentos, ultimoResumen.mejorPefNumero);
    }
});

function iniciarCapturaEnVivo() {
    const t = tema();
    Plotly.react(graficaVivoDiv, trazaVacia(t), {
        ...layoutBase(t),
        margin: { l: 44, r: 20, t: 10, b: 40 },
        xaxis: { ...layoutBase(t).xaxis, title: "Tiempo (s)" },
        yaxis: { ...layoutBase(t).yaxis, title: "Flujo (L/s)" },
    }, PLOTLY_CONFIG);
    estadoCaptura.textContent = "Adquiriendo datos. Realice la maniobra de espiración forzada.";
    btnIniciarSesion.disabled = true;
    btnNuevoIntento.disabled = true;
    btnDetener.disabled = false;
    btnFinalizarSesion.disabled = true;
}

const usarFechaManual = document.getElementById("usar-fecha-manual");
const fechaManualInput = document.getElementById("fecha-manual-input");

usarFechaManual.addEventListener("change", () => {
    fechaManualInput.disabled = !usarFechaManual.checked;
    if (usarFechaManual.checked && !fechaManualInput.value) {
        const ahora = new Date();
        ahora.setMinutes(ahora.getMinutes() - ahora.getTimezoneOffset());
        fechaManualInput.value = ahora.toISOString().slice(0, 16);
    }
});

btnIniciarSesion.addEventListener("click", () => {
    btnIniciarSesion.disabled = true;
    const fecha = usarFechaManual.checked && fechaManualInput.value ? fechaManualInput.value : null;
    socket.emit("iniciar_sesion", { fecha });
});

btnNuevoIntento.addEventListener("click", () => {
    iniciarCapturaEnVivo();
    socket.emit("iniciar_intento");
});

btnDetener.addEventListener("click", () => {
    socket.emit("detener_prueba");
});

btnFinalizarSesion.addEventListener("click", () => {
    socket.emit("finalizar_sesion");
    btnNuevoIntento.hidden = true;
    btnFinalizarSesion.hidden = true;
    estadoCaptura.textContent = "Sesión finalizada.";
});

socket.on("sesion_iniciada", (data) => {
    sesionActual = { idSesion: data.id_sesion, intentos: [], maxIntentos: data.max_intentos };
    tarjetaIntentos.hidden = true;
    listaIntentos.innerHTML = "";
    contadorIntentos.textContent = "";
    vistaToggle.hidden = true;
    tabResultados.disabled = true;
    mostrarVista("medicion");
    iniciarCapturaEnVivo();
    socket.emit("iniciar_intento");
});

socket.on("punto_en_vivo", (punto) => {
    Plotly.extendTraces(graficaVivoDiv, { x: [[punto.tiempo]], y: [[punto.flujo]] }, [0]);
});

socket.on("prueba_error", (data) => {
    estadoCaptura.textContent = data.mensaje;
    btnIniciarSesion.disabled = false;
    btnNuevoIntento.disabled = false;
    btnDetener.disabled = true;
});

socket.on("intento_completo", (data) => {
    sesionActual.intentos = data.sesion.intentos;

    btnIniciarSesion.disabled = true;
    btnNuevoIntento.disabled = false;
    btnDetener.disabled = true;

    const alMaximo = sesionActual.intentos.length >= sesionActual.maxIntentos;
    btnNuevoIntento.hidden = alMaximo;
    btnFinalizarSesion.hidden = false;
    btnFinalizarSesion.disabled = false;

    estadoCaptura.textContent = alMaximo
        ? `Intento completado. Se alcanzó el máximo de ${sesionActual.maxIntentos} intentos.`
        : "Intento completado.";

    contadorIntentos.textContent = `Intento ${sesionActual.intentos.length}` + (alMaximo ? " (máximo)" : "");

    renderizarListaIntentos(data.sesion);
    ultimoResumen = { resumen: data.sesion.resumen, intentos: sesionActual.intentos, mejorPefNumero: data.sesion.mejor_pef_intento };

    const primerIntento = sesionActual.intentos.length === 1;
    habilitarPasoResultados();
    // La vista debe hacerse visible ANTES de dibujar los gráficos: Plotly
    // calcula el ancho del contenedor en el momento de newPlot, y un div con
    // hidden (ancho 0) produce un gráfico con tamaño incorrecto que luego
    // desborda la página aunque el layout ya haya colapsado a una columna.
    if (primerIntento) mostrarVista("resultados");
    pintarResultados(ultimoResumen.resumen, ultimoResumen.intentos, ultimoResumen.mejorPefNumero);
});

function renderizarListaIntentos(sesion) {
    tarjetaIntentos.hidden = false;
    listaIntentos.innerHTML = sesion.intentos
        .map((intento) => {
            const esMejor = intento.es_mejor_pef || intento.es_mejor_fvc;
            const claseAceptable = intento.aceptable ? "badge-aceptable" : "badge-no-aceptable";
            const motivo = intento.motivo_no_aceptable ? ` — ${intento.motivo_no_aceptable}` : "";
            const marcadores = [
                intento.es_mejor_pef ? "Mejor PEF" : null,
                intento.es_mejor_fvc ? "Mejor FVC" : null,
            ].filter(Boolean).join(" · ");

            return `
                <div class="badge-intento ${esMejor ? "intento-mejor" : ""}">
                    <b>Intento ${intento.numero}</b>
                    <span class="status-badge ${claseAceptable}">${intento.aceptable ? "Aceptable" : "Revisar"}${motivo}</span>
                    <span class="metric-sub">PEF ${intento.pef_real.toFixed(2)} L/s · FVC ${intento.fvc.toFixed(2)} L${marcadores ? " · " + marcadores : ""}</span>
                </div>`;
        })
        .join("");
}

function pintarResultados(resumen, intentos, mejorPefNumero) {
    const t = tema();

    document.getElementById("valor-pef").textContent = resumen.pef_real.toFixed(2) + " L/s";
    document.getElementById("valor-pef-teorico").textContent = resumen.pef_teorico.toFixed(2) + " L/s";
    document.getElementById("valor-fvc").textContent = resumen.fvc.toFixed(2) + " L";
    document.getElementById("valor-fev1").textContent = resumen.fev1.toFixed(2) + " L";
    document.getElementById("valor-fev1-fvc").textContent = resumen.fev1_fvc_pct.toFixed(1) + "%";

    const badge = document.getElementById("badge-diagnostico");
    badge.textContent = resumen.texto_diagnostico;
    badge.className = "status-badge " + resumen.clase_badge;

    const repetibilidadTexto = resumen.repetible === null
        ? "No evaluable (se necesitan 2+ intentos)"
        : resumen.repetible
            ? `Sí (Δ FVC ${(resumen.diferencia_fvc * 1000).toFixed(0)} mL)`
            : `No (Δ FVC ${(resumen.diferencia_fvc * 1000).toFixed(0)} mL, límite 150 mL)`;

    document.getElementById("detalle-analitico").innerHTML = `
        <p class="metric-label">Detalle analítico</p>
        <div class="detalle-grid">
            <div><p class="metric-label">FEF 25-75%</p><b>${resumen.fef25_75.toFixed(2)} L/s</b></div>
            <div><p class="metric-label">Repetibilidad entre intentos</p><b>${repetibilidadTexto}</b></div>
        </div>`;

    pintarPanelIA(intentos.find((i) => i.es_mejor_fvc) || intentos[intentos.length - 1]);

    Plotly.newPlot(
        "grafica-gauge",
        [
            {
                type: "indicator",
                mode: "gauge+number+delta",
                value: resumen.rendimiento_pct,
                domain: { x: [0, 1], y: [0, 1] },
                delta: { reference: 100, decreasing: { color: t.critical } },
                number: { suffix: "%", font: { size: 32, color: t.ink } },
                gauge: {
                    axis: { range: [0, 120], tickvals: [0, 50, 80, 100, 120], tickfont: { color: t.inkMuted, size: 11 } },
                    bar: { color: t.accent, thickness: 0.22 },
                    bgcolor: t.border,
                    borderwidth: 0,
                    steps: [
                        { range: [0, 50], color: t.criticalSoft },
                        { range: [50, 80], color: t.warnSoft },
                        { range: [80, 120], color: t.okSoft },
                    ],
                },
            },
        ],
        { margin: { l: 40, r: 40, t: 16, b: 8 }, height: 190, autosize: true, paper_bgcolor: "rgba(0,0,0,0)" },
        PLOTLY_CONFIG
    );

    const layoutCurvas = layoutBase(t);

    const mejorIntento = intentos.find((i) => i.numero === mejorPefNumero) || intentos[intentos.length - 1];
    const volumenMax = Math.max(...mejorIntento.volumen, 0.001);
    Plotly.newPlot(
        "grafica-volumen-tiempo",
        [
            {
                x: mejorIntento.tiempo,
                y: mejorIntento.volumen,
                mode: "lines",
                line: { color: t.accent, width: 2.5, shape: "spline" },
                fill: "tozeroy",
                fillcolor: t.accent + "14",
            },
        ],
        {
            ...layoutCurvas,
            margin: { l: 44, r: 20, t: 15, b: 40 },
            xaxis: { ...layoutCurvas.xaxis, title: "Tiempo (s)" },
            yaxis: { ...layoutCurvas.yaxis, title: "Volumen (L)" },
            shapes: [
                {
                    type: "line",
                    x0: mejorIntento.tiempo_en_pef,
                    x1: mejorIntento.tiempo_en_pef,
                    y0: 0,
                    y1: volumenMax,
                    line: { color: t.critical, dash: "dash", width: 1.5 },
                },
            ],
        },
        PLOTLY_CONFIG
    );

    renderizarOverlayFlujoVolumen(intentos, mejorPefNumero, layoutCurvas, t);
}

function pintarPanelIA(intento) {
    const contenedor = document.getElementById("ia-contenido");
    const ia = intento.ia;

    if (!ia || !ia.disponible) {
        const motivo = ia && ia.motivo ? ia.motivo : "El modelo de IA no está disponible en este servidor.";
        contenedor.innerHTML = `<p class="ia-placeholder">${motivo}</p>`;
        return;
    }

    const avisoSimulado = intento.perfil_simulado
        ? `<p class="ia-aviso">Intento generado en modo simulación (perfil "${intento.perfil_simulado}"):
           esta predicción no es representativa de un caso real, solo sirve para verificar
           que el pipeline de IA funciona.</p>`
        : "";

    const badgeDeteccion = ia.copd_detectado
        ? `<span class="status-badge badge-roja">Patrón sugestivo de EPOC</span>`
        : `<span class="status-badge badge-verde">Sin señal de EPOC activo</span>`;

    let filaRiesgo = "";
    if (!ia.copd_detectado && ia.riesgo_1_5_anios) {
        const [r1, r2, r3, r4, r5] = ia.riesgo_1_5_anios;
        filaRiesgo = `
            <p class="metric-label" style="margin-top: 10px;">Riesgo futuro estimado (SpiroPredictor)</p>
            <div class="ia-riesgo-grid">
                <div><p class="metric-label">1 año</p><b>${(r1 * 100).toFixed(1)}%</b></div>
                <div><p class="metric-label">2 años</p><b>${(r2 * 100).toFixed(1)}%</b></div>
                <div><p class="metric-label">3 años</p><b>${(r3 * 100).toFixed(1)}%</b></div>
                <div><p class="metric-label">4 años</p><b>${(r4 * 100).toFixed(1)}%</b></div>
                <div><p class="metric-label">5+ años</p><b>${(r5 * 100).toFixed(1)}%</b></div>
            </div>`;
    }

    contenedor.innerHTML = `
        ${avisoSimulado}
        <div class="ia-deteccion">${badgeDeteccion}</div>
        <p class="metric-sub">Basado en el intento ${intento.numero} (mejor FVC de la sesión).</p>
        ${filaRiesgo}`;
}

function renderizarOverlayFlujoVolumen(intentos, mejorPefNumero, layoutCurvas, t) {
    const trazas = intentos.map((intento, idx) => {
        const esMejor = intento.numero === mejorPefNumero;
        return {
            x: intento.volumen,
            y: intento.flujo,
            mode: "lines",
            name: `Intento ${intento.numero}`,
            line: {
                color: esMejor ? t.accent : PALETA_INTENTOS[idx % PALETA_INTENTOS.length],
                width: esMejor ? 3 : 1.75,
                shape: "spline",
            },
            opacity: esMejor ? 1 : 0.75,
        };
    });

    const mejorIntento = intentos.find((i) => i.numero === mejorPefNumero);
    trazas.push({
        x: [mejorIntento.volumen_en_pef],
        y: [mejorIntento.pef_real],
        mode: "markers",
        name: "PEF",
        marker: { color: t.critical, size: 9, line: { color: t.surface, width: 2 } },
    });

    Plotly.newPlot(
        "grafica-flujo-volumen",
        trazas,
        {
            ...layoutCurvas,
            margin: { l: 44, r: 20, t: 15, b: 40 },
            xaxis: { ...layoutCurvas.xaxis, title: "Volumen (L)" },
            yaxis: { ...layoutCurvas.yaxis, title: "Flujo (L/s)" },
            showlegend: true,
            legend: { font: { color: t.inkMuted, size: 11 } },
        },
        PLOTLY_CONFIG
    );
}
