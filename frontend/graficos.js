// Carrega a distribuição de navegador copiada pelo comando documentado no README.
let carregamentoChart = null;
const instanciasGraficos = new Map();

function carregarChart() {
  if (window.Chart) return Promise.resolve(window.Chart);
  if (!carregamentoChart) {
    carregamentoChart = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "/vendor/chart.umd.min.js";
      script.onload = () => {
        if (window.Chart) resolve(window.Chart);
        else {
          carregamentoChart = null;
          reject(new Error("Chart.js não foi inicializado."));
        }
      };
      script.onerror = () => {
        script.remove();
        carregamentoChart = null;
        reject(new Error("Chart.js indisponível. Copie o arquivo para frontend/vendor."));
      };
      document.head.appendChild(script);
    });
  }
  return carregamentoChart;
}

export function destruirGraficos() {
  for (const chart of instanciasGraficos.values()) chart.destroy();
  instanciasGraficos.clear();
}

export async function renderizarGraficos(bolha, graficos = []) {
  if (!Array.isArray(graficos) || !graficos.length) return;
  // Chamado após o evento final; repaints de tokens tardios são ignorados.
  const container = document.createElement("div");
  container.style.cssText = "width:100%;min-width:0;grid-column:1/-1;";
  bolha.appendChild(container);

  for (const grafico of graficos) {
    const card = document.createElement("figure");
    card.style.cssText = "margin:16px 0;padding:12px;border:1px solid #64748b;border-radius:12px;min-width:0;";
    const area = document.createElement("div");
    area.style.cssText = "position:relative;height:320px;width:100%;min-width:0;";
    const canvas = document.createElement("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", grafico.titulo || "Gráfico");
    area.appendChild(canvas);
    card.appendChild(area);

    const fonte = document.createElement("figcaption");
    fonte.textContent = "Fonte: " + (grafico.fonte || "Consulta da planilha");
    card.appendChild(fonte);

    // Tabela disponível inclusive se o carregamento do Chart.js falhar.
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Ver dados do gráfico";
    details.appendChild(summary);
    const table = document.createElement("table");
    const config = grafico.config;
    if (!config || !Array.isArray(config.data?.labels) || !Array.isArray(config.data?.datasets)) continue;
    const cabecalho = table.createTHead().insertRow();
    for (const label of ["Categoria", ...config.data.datasets.map(s => s.label)]) {
      const th = document.createElement("th");
      th.textContent = label;
      th.scope = "col";
      cabecalho.appendChild(th);
    }
    const body = table.createTBody();
    config.data.labels.forEach((label, i) => {
      const row = body.insertRow();
      for (const valor of [label, ...config.data.datasets.map(s => s.data[i])]) {
        row.insertCell().textContent = valor ?? "—";
      }
    });
    const wrap = document.createElement("div");
    wrap.style.overflowX = "auto";
    wrap.appendChild(table);
    details.appendChild(wrap);
    card.appendChild(details);
    container.appendChild(card);
    try {
      const Chart = await carregarChart();
      if (!canvas.isConnected) continue;
      const copia = JSON.parse(JSON.stringify(config));
      const corTexto = getComputedStyle(bolha).color;
      copia.options = copia.options || {};
      copia.options.color = corTexto;
      if (copia.options.plugins?.title) copia.options.plugins.title.color = corTexto;
      if (copia.options.scales) {
        for (const eixo of Object.values(copia.options.scales)) eixo.ticks = {color: corTexto};
        copia.options.scales.x = {ticks: {color: corTexto}};
      }
      instanciasGraficos.set(canvas, new Chart(canvas, copia));
    } catch (erro) {
      area.textContent = erro.message;
      details.open = true;
    }
  }
}
