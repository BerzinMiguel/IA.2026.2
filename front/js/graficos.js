/* =========================================================
   graficos.js — Gráficos simples em SVG (sem biblioteca)
   ========================================================= */

/*
  desenharGraficoLinha(idContainer, series)
  series: [ { nome, cor (hex ou "var(--x)"), pontos: [ { x: "2026-11-01", y: 37.2 }, ... ] } ]
  Todas as séries devem ter os mesmos valores de x.
*/
function desenharGraficoLinha(idContainer, series) {
  const container = document.getElementById(idContainer);
  if (!container) return;

  const todos = series.flatMap(s => s.pontos);
  if (todos.length === 0) {
    container.innerHTML = "Sem dados para exibir";
    return;
  }

  const L = 800, A = 280, M = { topo: 20, dir: 20, base: 30, esq: 55 };
  const ys = todos.map(p => p.y);
  let min = Math.min(...ys), max = Math.max(...ys);
  if (min === max) { min -= 1; max += 1; }
  const n = series[0].pontos.length;

  const px = i => M.esq + (i / Math.max(n - 1, 1)) * (L - M.esq - M.dir);
  const py = v => M.topo + (1 - (v - min) / (max - min)) * (A - M.topo - M.base);

  // Linhas de grade + rótulos do eixo Y
  let grade = "";
  for (let k = 0; k <= 4; k++) {
    const v = min + (k / 4) * (max - min);
    const y = py(v);
    grade += `<line x1="${M.esq}" x2="${L - M.dir}" y1="${y}" y2="${y}" style="stroke:var(--grade)"/>
              <text x="${M.esq - 8}" y="${y + 4}" style="fill:var(--texto-suave)" font-size="11" text-anchor="end">${v.toFixed(2)}</text>`;
  }

  // Rótulos do eixo X (início, meio, fim)
  const xs = series[0].pontos;
  const rotulosX = [0, Math.floor((n - 1) / 2), n - 1]
    .map((i, k) => `<text x="${px(i)}" y="${A - 8}" style="fill:var(--texto-suave)" font-size="11" text-anchor="${["start", "middle", "end"][k]}">${formatarData(xs[i].x)}</text>`)
    .join("");

  const linhas = series.map(s => {
    const d = s.pontos.map((p, i) => `${i === 0 ? "M" : "L"}${px(i).toFixed(1)},${py(p.y).toFixed(1)}`).join(" ");
    return `<path d="${d}" fill="none" style="stroke:${s.cor}" stroke-width="2" stroke-linejoin="round"/>`;
  }).join("");

  container.innerHTML = `<svg viewBox="0 0 ${L} ${A}" preserveAspectRatio="none">${grade}${rotulosX}${linhas}</svg>`;
}

/*
  desenharGraficoBarras(idContainer, pontos)
  pontos: [ { x: "2026-11-01", y: 0.25 }, ... ]  (y pode ser negativo)
  Usado para o erro da previsão por dia.
*/
function desenharGraficoBarras(idContainer, pontos) {
  const container = document.getElementById(idContainer);
  if (!container) return;
  if (!pontos.length) {
    container.innerHTML = "Sem dados para exibir";
    return;
  }

  const L = 800, A = 280, M = { topo: 20, dir: 20, base: 30, esq: 55 };
  const maxAbs = Math.max(...pontos.map(p => Math.abs(p.y))) || 1;
  const zero = M.topo + (A - M.topo - M.base) / 2;
  const escala = (A - M.topo - M.base) / 2 / maxAbs;
  const largura = (L - M.esq - M.dir) / pontos.length;

  const barras = pontos.map((p, i) => {
    const h = Math.abs(p.y) * escala;
    const y = p.y >= 0 ? zero - h : zero;
    const cor = p.y >= 0 ? "var(--positivo)" : "var(--negativo)";
    return `<rect x="${M.esq + i * largura + 1}" y="${y}" width="${Math.max(largura - 2, 1)}" height="${h}" style="fill:${cor}" opacity=".85"/>`;
  }).join("");

  const eixo = `<line x1="${M.esq}" x2="${L - M.dir}" y1="${zero}" y2="${zero}" style="stroke:var(--titulo)"/>
    <text x="${M.esq - 8}" y="${zero + 4}" style="fill:var(--texto-suave)" font-size="11" text-anchor="end">0</text>
    <text x="${M.esq - 8}" y="${M.topo + 4}" style="fill:var(--texto-suave)" font-size="11" text-anchor="end">${maxAbs.toFixed(2)}</text>
    <text x="${M.esq - 8}" y="${A - M.base + 4}" style="fill:var(--texto-suave)" font-size="11" text-anchor="end">-${maxAbs.toFixed(2)}</text>`;

  container.innerHTML = `<svg viewBox="0 0 ${L} ${A}" preserveAspectRatio="none">${eixo}${barras}</svg>`;
}