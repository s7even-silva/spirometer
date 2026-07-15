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
        Plotly.Plots.resize(div);
    });
}

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
    // no dispara resize). Se reintenta en dos momentos porque un solo
    // requestAnimationFrame a veces calcula el ancho antes de que el
    // navegador termine el reflow (sobre todo con zoom de página activo),
    // dejando el gauge con las etiquetas del arco cortadas.
    const contenedorId = nombre === "medicion" ? "vista-medicion" : "vista-resultados";
    requestAnimationFrame(() => redimensionarGraficas(contenedorId));
    setTimeout(() => redimensionarGraficas(contenedorId), 150);
}

// Si el usuario hace zoom (Ctrl+rueda) o redimensiona la ventana mientras ya
// está viendo una vista con gráficos, Plotly no se entera solo: sin este
// listener el gauge queda con el tamaño calculado para el zoom anterior.
let resizeTimeout = null;
window.addEventListener("resize", () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        redimensionarGraficas(vistaResultados.hidden ? "vista-medicion" : "vista-resultados");
    }, 150);
});

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
