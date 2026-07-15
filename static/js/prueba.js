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

const layoutVivo = {
    margin: { l: 40, r: 20, t: 10, b: 40 },
    xaxis: { title: "Tiempo (s)", showgrid: true, gridcolor: "#E2E8F0" },
    yaxis: { title: "Flujo (L/s)", showgrid: true, gridcolor: "#E2E8F0" },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "white",
};

Plotly.newPlot(graficaVivoDiv, [{ x: [], y: [], mode: "lines", line: { color: "#4F46E5", width: 3 } }], layoutVivo);

let sesionActual = { idSesion: null, intentos: [], maxIntentos: Infinity };

function iniciarCapturaEnVivo() {
    Plotly.react(graficaVivoDiv, [{ x: [], y: [], mode: "lines", line: { color: "#4F46E5", width: 3 } }], layoutVivo);
    estadoCaptura.textContent = "💨 Adquiriendo datos... ¡Sople con fuerza!";
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
    estadoCaptura.textContent = "🏁 Sesión finalizada.";
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
    estadoCaptura.textContent = "⚠️ " + data.mensaje;
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
        ? `✅ Intento completado. Se alcanzó el máximo de ${sesionActual.maxIntentos} intentos.`
        : "✅ Intento completado.";

    contadorIntentos.textContent = `Intento ${sesionActual.intentos.length}` + (alMaximo ? " (máximo)" : "");

    renderizarListaIntentos(data.sesion);
    mostrarResultados(data.sesion.resumen, sesionActual.intentos, data.sesion.mejor_pef_intento);
});

function renderizarListaIntentos(sesion) {
    tarjetaIntentos.hidden = false;
    listaIntentos.innerHTML = sesion.intentos
        .map((intento) => {
            const esMejor = intento.es_mejor_pef || intento.es_mejor_fvc;
            const claseAceptable = intento.aceptable ? "badge-aceptable" : "badge-no-aceptable";
            const icono = intento.aceptable ? "✔️" : "⚠️";
            const motivo = intento.motivo_no_aceptable ? ` — ${intento.motivo_no_aceptable}` : "";
            const marcadores = [
                intento.es_mejor_pef ? "Mejor PEF" : null,
                intento.es_mejor_fvc ? "Mejor FVC" : null,
            ].filter(Boolean).join(" · ");

            return `
                <div class="badge-intento ${esMejor ? "intento-mejor" : ""}">
                    <b>Intento ${intento.numero}</b>
                    <span class="status-badge ${claseAceptable}">${icono} ${intento.aceptable ? "Aceptable" : "Revisar"}${motivo}</span>
                    <span class="metric-sub">PEF ${intento.pef_real.toFixed(2)} L/s · FVC ${intento.fvc.toFixed(2)} L${marcadores ? " · " + marcadores : ""}</span>
                </div>`;
        })
        .join("");
}

function mostrarResultados(resumen, intentos, mejorPefNumero) {
    resultados.hidden = false;

    document.getElementById("valor-pef").textContent = resumen.pef_real.toFixed(2) + " L/s";
    document.getElementById("valor-pef-teorico").textContent = resumen.pef_teorico.toFixed(2) + " L/s";
    document.getElementById("valor-fvc").textContent = resumen.fvc.toFixed(2) + " L";
    document.getElementById("valor-fev1").textContent = resumen.fev1.toFixed(2) + " L";
    document.getElementById("valor-fev1-fvc").textContent = resumen.fev1_fvc_pct.toFixed(1) + "%";

    const badge = document.getElementById("badge-diagnostico");
    badge.textContent = resumen.texto_diagnostico;
    badge.className = "status-badge " + resumen.clase_badge;

    document.getElementById("detalle-analitico").innerHTML = `
        <p class="metric-label">Lectura Analítica de Soporte</p>
        <div class="detalle-grid">
            <div><p class="metric-label">Flujo Máximo Real (PEF)</p><b>${resumen.pef_real.toFixed(2)} L/s</b></div>
            <div><p class="metric-label">Meta según Tabla Médica</p><b>${resumen.pef_teorico.toFixed(2)} L/s</b></div>
            <div><p class="metric-label">Volumen Expirado (FVC)</p><b>${resumen.fvc.toFixed(2)} L</b></div>
            <div><p class="metric-label">FEF 25-75%</p><b>${resumen.fef25_75.toFixed(2)} L/s</b></div>
        </div>`;

    Plotly.newPlot(
        "grafica-gauge",
        [
            {
                type: "indicator",
                mode: "gauge+number+delta",
                value: resumen.rendimiento_pct,
                delta: { reference: 100, decreasing: { color: "#EF4444" } },
                number: { suffix: "%", font: { size: 40, color: "#1E293B" } },
                gauge: {
                    axis: { range: [0, 120], tickvals: [0, 50, 80, 100, 120] },
                    bar: { color: "#4F46E5", thickness: 0.22 },
                    bgcolor: "#F1F5F9",
                    borderwidth: 0,
                    steps: [
                        { range: [0, 50], color: "rgba(239, 68, 68, 0.15)" },
                        { range: [50, 80], color: "rgba(234, 179, 8, 0.15)" },
                        { range: [80, 120], color: "rgba(34, 197, 94, 0.15)" },
                    ],
                },
            },
        ],
        { margin: { l: 10, r: 10, t: 10, b: 10 }, height: 220, paper_bgcolor: "rgba(0,0,0,0)" }
    );

    const layoutPremium = {
        plot_bgcolor: "white",
        paper_bgcolor: "rgba(0,0,0,0)",
        margin: { l: 40, r: 20, t: 15, b: 40 },
        xaxis: { showgrid: true, gridcolor: "#E2E8F0", zeroline: false },
        yaxis: { showgrid: true, gridcolor: "#E2E8F0", zeroline: false },
    };

    const mejorIntento = intentos.find((i) => i.numero === mejorPefNumero) || intentos[intentos.length - 1];
    const volumenMax = Math.max(...mejorIntento.volumen, 0.001);
    Plotly.newPlot(
        "grafica-volumen-tiempo",
        [
            {
                x: mejorIntento.tiempo,
                y: mejorIntento.volumen,
                mode: "lines",
                line: { color: "#4F46E5", width: 3, shape: "spline" },
                fill: "tozeroy",
                fillcolor: "rgba(79, 70, 229, 0.06)",
            },
        ],
        {
            ...layoutPremium,
            xaxis: { ...layoutPremium.xaxis, title: "Tiempo (segundos)" },
            yaxis: { ...layoutPremium.yaxis, title: "Volumen (Litros)" },
            shapes: [
                {
                    type: "line",
                    x0: mejorIntento.tiempo_en_pef,
                    x1: mejorIntento.tiempo_en_pef,
                    y0: 0,
                    y1: volumenMax,
                    line: { color: "#EF4444", dash: "dash", width: 1.5 },
                },
            ],
        }
    );

    renderizarOverlayFlujoVolumen(intentos, mejorPefNumero, layoutPremium);
}

function renderizarOverlayFlujoVolumen(intentos, mejorPefNumero, layoutPremium) {
    const trazas = intentos.map((intento) => {
        const esMejor = intento.numero === mejorPefNumero;
        return {
            x: intento.volumen,
            y: intento.flujo,
            mode: "lines",
            name: `Intento ${intento.numero}`,
            line: {
                color: esMejor ? "#EC4899" : "#94A3B8",
                width: esMejor ? 3 : 1.5,
                shape: "spline",
            },
            opacity: esMejor ? 1 : 0.5,
        };
    });

    const mejorIntento = intentos.find((i) => i.numero === mejorPefNumero);
    trazas.push({
        x: [mejorIntento.volumen_en_pef],
        y: [mejorIntento.pef_real],
        mode: "markers",
        name: "PEF",
        marker: { color: "#EF4444", size: 10, line: { color: "white", width: 2 } },
    });

    Plotly.newPlot(
        "grafica-flujo-volumen",
        trazas,
        {
            ...layoutPremium,
            xaxis: { ...layoutPremium.xaxis, title: "Volumen (Litros)" },
            yaxis: { ...layoutPremium.yaxis, title: "Flujo (L/s)" },
            showlegend: true,
        }
    );
}
