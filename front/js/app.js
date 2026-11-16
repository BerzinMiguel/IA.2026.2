/* =========================================================
   app.js — Controle das telas e preenchimento dos dados
   ========================================================= */

/* ===== Utilitários de formatação ===== */
function formatarData(iso) {
  if (!iso) return "--/--/----";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

function formatarMoeda(valor) {
  return Number(valor).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatarNumero(valor, casas = 2) {
  return Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

function formatarPercentual(valor) {
  const sinal = valor > 0 ? "+" : "";
  return `${sinal}${formatarNumero(valor, 2)} %`;
}

function calcularVariacao(atual, previsto) {
  return ((previsto / atual) - 1) * 100;
}

/* ===== Tema claro / escuro ===== */
function obterTema() {
  return document.documentElement.getAttribute("data-tema") || "claro";
}

function aplicarTema(tema) {
  document.documentElement.setAttribute("data-tema", tema);
  try { localStorage.setItem("tema", tema); } catch (e) {}
}

function alternarTema() {
  aplicarTema(obterTema() === "escuro" ? "claro" : "escuro");
}

/* ===== Navegação entre telas ===== */
function trocarTela(idTela) {
  document.querySelectorAll(".tela").forEach(t => t.classList.toggle("ativa", t.id === idTela));
  document.querySelectorAll(".aba").forEach(a => a.classList.toggle("ativa", a.dataset.tela === idTela));
}

/* ===== TELA 1: DASHBOARD ===== */
function exibirRecomendacao(previsao) {
  const card = document.getElementById("card-recomendacao");
  card.classList.remove("aplicar", "manter", "retirar");
  card.classList.add(previsao.recomendacao.toLowerCase());

  document.getElementById("recomendacao-texto").textContent = previsao.recomendacao;
  document.getElementById("fechamento-previsto").textContent = formatarMoeda(previsao.fechamento_previsto);
  document.getElementById("variacao-prevista").textContent = formatarPercentual(previsao.variacao_prevista_pct);
  document.getElementById("data-alvo").textContent = formatarData(previsao.data_alvo);
  document.getElementById("aviso").textContent = previsao.aviso;
  document.getElementById("data-atualizacao").textContent = formatarData(previsao.data_atualizacao);
}

function exibirIndicador(nome, dados) {
  const card = document.getElementById(`indicador-${nome}`);
  const formatar = nome === "volatilidade" ? v => formatarNumero(v, 2) + " %" : v => formatarMoeda(v);
  const variacao = calcularVariacao(dados.atual, dados.previsto);

  card.querySelector(".valor-atual").textContent = formatar(dados.atual);
  card.querySelector(".valor-previsto").textContent = formatar(dados.previsto);

  const selo = card.querySelector(".variacao");
  selo.textContent = formatarPercentual(variacao);
  selo.classList.remove("positiva", "negativa");
  if (variacao > 0) selo.classList.add("positiva");
  if (variacao < 0) selo.classList.add("negativa");
}

function exibirIndicadores(indicadores) {
  exibirIndicador("dolar", indicadores.dolar);
  exibirIndicador("bolsa", indicadores.bolsa);
  exibirIndicador("volatilidade", indicadores.volatilidade);
}

async function carregarDashboard() {
  const previsao = await buscarPrevisaoAtual();
  exibirRecomendacao(previsao);
  exibirIndicadores(previsao.indicadores);

  const historico = await buscarHistorico("bolsa", 30);
  desenharGraficoLinha("grafico-resumo", [
    { nome: "Bolsa", cor: "var(--titulo)", pontos: historico.map(h => ({ x: h.data, y: h.valor })) },
  ]);
}

/* ===== TELA 2: HISTÓRICO ===== */
async function atualizarGraficoHistorico() {
  const indicador = document.getElementById("filtro-indicador").value;
  const dias = Number(document.getElementById("filtro-periodo").value);
  const historico = await buscarHistorico(indicador, dias);

  desenharGraficoLinha("grafico-historico", [
    { nome: indicador, cor: "var(--titulo)", pontos: historico.map(h => ({ x: h.data, y: h.valor })) },
  ]);
}

function exibirGraficoComparativo(avaliacao) {
  desenharGraficoLinha("grafico-comparativo", [
    { nome: "Real", cor: "var(--titulo)", pontos: avaliacao.map(a => ({ x: a.data_alvo, y: a.real })) },
    { nome: "Previsto", cor: "var(--dourado)", pontos: avaliacao.map(a => ({ x: a.data_alvo, y: a.previsto })) },
  ]);
}

function preencherTabelaRecomendacoes(lista) {
  const corpo = document.getElementById("tabela-recomendacoes");
  if (!lista.length) {
    corpo.innerHTML = `<tr><td colspan="4" class="vazio">Sem dados</td></tr>`;
    return;
  }
  corpo.innerHTML = lista.map(r => `
    <tr>
      <td>${formatarData(r.data)}</td>
      <td>${formatarMoeda(r.fechamento_previsto)}</td>
      <td>${formatarPercentual(r.variacao_prevista_pct)}</td>
      <td><span class="selo ${r.recomendacao.toLowerCase()}">${r.recomendacao}</span></td>
    </tr>`).join("");
}

async function carregarHistorico() {
  await atualizarGraficoHistorico();
  const [avaliacao, recomendacoes] = await Promise.all([buscarAvaliacao(), buscarRecomendacoes(30)]);
  exibirGraficoComparativo(avaliacao);
  preencherTabelaRecomendacoes(recomendacoes);
}

/* ===== TELA 3: DESEMPENHO DA IA ===== */
function exibirMetricas(m) {
  document.getElementById("metrica-mae").textContent = formatarNumero(m.MAE, 3);
  document.getElementById("metrica-rmse").textContent = formatarNumero(m.RMSE, 3);
  document.getElementById("metrica-mape").textContent = formatarNumero(m.MAPE_pct, 2) + " %";
  document.getElementById("metrica-amostras").textContent = `${m.amostras_treino} / ${m.amostras_teste}`;
  document.getElementById("metrica-observacao").textContent = m.observacao || "";
}

function preencherTabelaAvaliacao(avaliacao) {
  const corpo = document.getElementById("tabela-avaliacao");
  if (!avaliacao.length) {
    corpo.innerHTML = `<tr><td colspan="4" class="vazio">Sem dados</td></tr>`;
    return;
  }
  corpo.innerHTML = avaliacao.slice().reverse().map(a => `
    <tr>
      <td>${formatarData(a.data_alvo)}</td>
      <td>${formatarMoeda(a.real)}</td>
      <td>${formatarMoeda(a.previsto)}</td>
      <td>${formatarNumero(a.erro, 3)}</td>
    </tr>`).join("");
}

async function carregarDesempenho() {
  const [metricas, avaliacao] = await Promise.all([buscarMetricas(), buscarAvaliacao()]);
  exibirMetricas(metricas);
  preencherTabelaAvaliacao(avaliacao);
  desenharGraficoBarras("grafico-erro", avaliacao.map(a => ({ x: a.data_alvo, y: a.erro })));
}

/* ===== Atualização diária ===== */
async function atualizarTudo() {
  const botao = document.getElementById("btn-atualizar");
  botao.disabled = true;
  botao.textContent = "Atualizando...";
  try {
    await solicitarAtualizacao();
    await carregarTudo();
  } catch (erro) {
    mostrarErro(erro);
  } finally {
    botao.disabled = false;
    botao.textContent = "Atualizar";
  }
}

async function carregarTudo() {
  await Promise.all([carregarDashboard(), carregarHistorico(), carregarDesempenho()]);
}

function mostrarErro(erro) {
  console.error(erro);
  document.getElementById("aviso").textContent = "Não foi possível carregar os dados: " + erro.message;
}

/* ===== Inicialização ===== */
function iniciar() {
  document.querySelectorAll(".aba").forEach(aba =>
    aba.addEventListener("click", () => trocarTela(aba.dataset.tela))
  );
  document.getElementById("btn-atualizar").addEventListener("click", atualizarTudo);
  document.getElementById("btn-tema").addEventListener("click", alternarTema);
  document.getElementById("filtro-indicador").addEventListener("change", atualizarGraficoHistorico);
  document.getElementById("filtro-periodo").addEventListener("change", atualizarGraficoHistorico);

  carregarTudo().catch(mostrarErro);
}

document.addEventListener("DOMContentLoaded", iniciar);