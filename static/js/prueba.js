const socket = io();

const graficaVivoDiv = document.getElementById("grafica-vivo");
const btnIniciar = document.getElementById("btn-iniciar");
const btnDetener = document.getElementById("btn-detener");
const estadoCaptura = document.getElementById("estado-captura");
const resultados = document.getElementById("resultados");

const layoutVivo = {
    margin: { l: 40, r: 20, t: 10, b: 40 },
    xaxis: { title: "Tiempo (s)", showgrid: true, gridcolor: "#E2E8F0" },
    yaxis: { title: "Flujo (L/s)", showgrid: true, gridcolor: "#E2E8F0" },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "white",
};

Plotly.newPlot(graficaVivoDiv, [{ x: [], y: [], mode: "lines", line: { color: "#4F46E5", width: 3 } }], layoutVivo);

btnIniciar.addEventListener("click", () => {
    Plotly.react(graficaVivoDiv, [{ x: [], y: [], mode: "lines", line: { color: "#4F46E5", width: 3 } }], layoutVivo);
    resultados.hidden = true;
    estadoCaptura.textContent = "💨 Adquiriendo datos... ¡Sople con fuerza!";
    btnIniciar.disabled = true;
    btnDetener.disabled = false;
    socket.emit("iniciar_prueba");
});

btnDetener.addEventListener("click", () => {
    socket.emit("detener_prueba");
});

socket.on("punto_en_vivo", (punto) => {
    Plotly.extendTraces(graficaVivoDiv, { x: [[punto.tiempo]], y: [[punto.flujo]] }, [0]);
});

socket.on("prueba_error", (data) => {
    estadoCaptura.textContent = "⚠️ " + data.mensaje;
    btnIniciar.disabled = false;
    btnDetener.disabled = true;
});

socket.on("prueba_completa", (metricas) => {
    btnIniciar.disabled = false;
    btnDetener.disabled = true;
    estadoCaptura.textContent = "✅ Prueba completada.";
    mostrarResultados(metricas);
});

function mostrarResultados(m) {
    resultados.hidden = false;

    document.getElementById("valor-pef").textContent = m.pef_real.toFixed(2) + " L/s";
    document.getElementById("valor-pef-teorico").textContent = m.pef_teorico.toFixed(2) + " L/s";
    document.getElementById("valor-fvc").textContent = m.fvc.toFixed(2) + " L";
    document.getElementById("valor-fev1").textContent = m.fev1.toFixed(2) + " L";
    document.getElementById("valor-fev1-fvc").textContent = m.fev1_fvc_pct.toFixed(1) + "%";

    const badge = document.getElementById("badge-diagnostico");
    badge.textContent = m.texto_diagnostico;
    badge.className = "status-badge " + m.clase_badge;

    document.getElementById("detalle-analitico").innerHTML = `
        <p class="metric-label">Lectura Analítica de Soporte</p>
        <div class="detalle-grid">
            <div><p class="metric-label">Flujo Máximo Real (PEF)</p><b>${m.pef_real.toFixed(2)} L/s</b></div>
            <div><p class="metric-label">Meta según Tabla Médica</p><b>${m.pef_teorico.toFixed(2)} L/s</b></div>
            <div><p class="metric-label">Volumen Expirado (FVC)</p><b>${m.fvc.toFixed(2)} L</b></div>
        </div>`;

    Plotly.newPlot(
        "grafica-gauge",
        [
            {
                type: "indicator",
                mode: "gauge+number+delta",
                value: m.rendimiento_pct,
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

    const volumenMax = Math.max(...m.volumen, 0.001);
    Plotly.newPlot(
        "grafica-volumen-tiempo",
        [
            {
                x: m.tiempo,
                y: m.volumen,
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
                    x0: m.tiempo_en_pef,
                    x1: m.tiempo_en_pef,
                    y0: 0,
                    y1: volumenMax,
                    line: { color: "#EF4444", dash: "dash", width: 1.5 },
                },
            ],
        }
    );

    Plotly.newPlot(
        "grafica-flujo-volumen",
        [
            {
                x: m.volumen,
                y: m.flujo,
                mode: "lines",
                line: { color: "#EC4899", width: 3, shape: "spline" },
                fill: "tozeroy",
                fillcolor: "rgba(236, 72, 153, 0.06)",
            },
            {
                x: [m.volumen_en_pef],
                y: [m.pef_real],
                mode: "markers",
                marker: { color: "#EF4444", size: 10, line: { color: "white", width: 2 } },
            },
        ],
        {
            ...layoutPremium,
            xaxis: { ...layoutPremium.xaxis, title: "Volumen (Litros)" },
            yaxis: { ...layoutPremium.yaxis, title: "Flujo (L/s)" },
            showlegend: false,
        }
    );
}
