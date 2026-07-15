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
const resultados = document.getElementById("resultados");

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
        mostrarResultados(ultimoResumen.resumen, ultimoResumen.intentos, ultimoResumen.mejorPefNumero);
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

btnIniciarSesion.addEventListener("click", () => {
    btnIniciarSesion.disabled = true;
    socket.emit("iniciar_sesion");
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
    resultados.hidden = true;
    tarjetaIntentos.hidden = true;
    listaIntentos.innerHTML = "";
    contadorIntentos.textContent = "";
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
    mostrarResultados(ultimoResumen.resumen, ultimoResumen.intentos, ultimoResumen.mejorPefNumero);
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

function mostrarResultados(resumen, intentos, mejorPefNumero) {
    resultados.hidden = false;
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
                delta: { reference: 100, decreasing: { color: t.critical } },
                number: { suffix: "%", font: { size: 38, color: t.ink } },
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
        { margin: { l: 34, r: 34, t: 20, b: 10 }, height: 220, paper_bgcolor: "rgba(0,0,0,0)" },
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
    const trazas = intentos.map((intento) => {
        const esMejor = intento.numero === mejorPefNumero;
        return {
            x: intento.volumen,
            y: intento.flujo,
            mode: "lines",
            name: `Intento ${intento.numero}`,
            line: {
                color: esMejor ? t.accent : t.inkMuted,
                width: esMejor ? 2.5 : 1.25,
                shape: "spline",
            },
            opacity: esMejor ? 1 : 0.45,
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
