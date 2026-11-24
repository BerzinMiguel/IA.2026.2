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
/* O backend manda null quando ainda não há histórico avaliado (ou quando a IA
   simulada está ativa, que não tem amostras de treino). Melhor "--" que 0,000. */
function ouTraco(valor, formatar) {
  return (valor === null || valor === undefined) ? "--" : formatar(valor);
}

function exibirMetricas(m) {
  document.getElementById("metrica-mae").textContent = ouTraco(m.MAE, v => formatarNumero(v, 3));
  document.getElementById("metrica-rmse").textContent = ouTraco(m.RMSE, v => formatarNumero(v, 3));
  document.getElementById("metrica-mape").textContent = ouTraco(m.MAPE_pct, v => formatarNumero(v, 2) + " %");
  document.getElementById("metrica-amostras").textContent =
    `${ouTraco(m.amostras_treino, v => v)} / ${ouTraco(m.amostras_teste, v => v)}`;
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

/* ===== Atualização diária =====
   O backend só recalcula quando existe pregão novo: para uma data que já tem
   execução gravada ele devolve "ja_existia" em instantes. Sem dizer isso na
   tela, o botão parece quebrado quando na verdade não há o que processar. */
function mostrarStatus(texto, erro = false) {
  const alvo = document.getElementById("status-atualizacao");
  alvo.textContent = texto;
  alvo.classList.toggle("erro", erro);
  alvo.classList.toggle("oculto", !texto);
}

async function atualizarTudo() {
  const botao = document.getElementById("btn-atualizar");
  botao.disabled = true;
  botao.textContent = "Atualizando...";
  mostrarStatus("Buscando cotações novas e rodando o pipeline; leva alguns minutos.");
  try {
    const resposta = await solicitarAtualizacao();
    await carregarTudo();
    const data = formatarData(resposta.data_atualizacao);
    const s = resposta.sincronizacao;
    const baixadas = !s
      ? ""
      : s.pregoes_novos
        ? `${s.pregoes_novos} pregão(ões) novo(s) baixado(s), até ${formatarData(s.ultima_data)}. `
        : `Nenhum pregão novo nas fontes (base já ia até ${formatarData(s.ultima_data)}). `;
    mostrarStatus(baixadas + (resposta.status === "ja_existia"
      ? `A previsão de ${data} já existia, nada a recalcular.`
      : `Previsão de ${data} gerada: ${(resposta.recomendacao || "").toUpperCase()}.`));
  } catch (erro) {
    mostrarErro(erro);
    mostrarStatus("Falha ao atualizar: " + erro.message, true);
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

/* ===== TELA 1: MINHA POSIÇÃO =====
   A previsão é do mercado e igual para todos; só o enquadramento muda.
   Por isso nada aqui é gravado: o backend calcula e devolve na hora. */
const SINAIS = {
  alta:      { texto: "sinal de alta",  classe: "sinal-alta" },
  baixa:     { texto: "sinal de baixa", classe: "sinal-baixa" },
  sem_sinal: { texto: "sem sinal",      classe: "sinal-neutro" },
};

function linhaPosicao(rotulo, valor, destaque = false) {
  return `<div class="${destaque ? "item destaque" : "item"}">
            <span class="rotulo">${rotulo}</span><strong>${valor}</strong>
          </div>`;
}

function exibirPosicao(d) {
  const caixa = document.getElementById("resultado-posicao");
  caixa.classList.remove("oculto");

  const card = document.getElementById("card-posicao");
  card.classList.remove("aplicar", "aplicar-mais", "manter", "retirar");
  card.classList.add(d.recomendacao.toLowerCase().replace(/\s+/g, "-"));

  document.getElementById("posicao-recomendacao").textContent = d.recomendacao;

  const sinal = SINAIS[d.sinal] || SINAIS.sem_sinal;
  const selo = document.getElementById("posicao-sinal");
  selo.textContent = sinal.texto;
  selo.className = "selo-sinal " + sinal.classe;

  // O "porquê" em uma frase: é o que separa um conselho de um número solto.
  let explicacao;
  if (d.sinal === "sem_sinal" && d.erro_modelo_pct != null) {
    explicacao = `O modelo prevê ${formatarPercentual(d.variacao_prevista_pct)} e erra em média `
      + `${formatarNumero(d.erro_modelo_pct, 2)} %. O movimento previsto é menor que o erro, `
      + `então ele não distingue alta de baixa até ${formatarData(d.data_alvo)}.`;
  } else if (d.motivo_retirada) {
    explicacao = `Queda prevista acima do limiar de ${formatarNumero(d.limiar_pct, 1)} %: `
      + `retirar aqui é ${d.motivo_retirada}.`;
  } else if (d.sinal === "baixa") {
    explicacao = `Queda prevista, mas sem posição não há o que retirar: aguarde antes de aplicar.`;
  } else {
    explicacao = `Alta prevista acima do limiar de ${formatarNumero(d.limiar_pct, 1)} % `
      + `para ${formatarData(d.data_alvo)}.`;
  }
  document.getElementById("posicao-explicacao").textContent = explicacao;

  const faixa = d.faixa_preco
    ? `${formatarMoeda(d.faixa_preco[0])} a ${formatarMoeda(d.faixa_preco[1])}`
    : "--";
  let html = linhaPosicao("Preço hoje", formatarMoeda(d.preco_atual))
           + linhaPosicao("Previsto", formatarMoeda(d.preco_previsto))
           + linhaPosicao("Faixa típica de erro", faixa);

  if (d.posicao) {
    const p = d.posicao;
    html += linhaPosicao("Investido", formatarMoeda(p.valor_investido))
          + linhaPosicao("Valor hoje", `${formatarMoeda(p.valor_atual)} (${formatarPercentual(p.resultado_atual_pct)})`)
          + linhaPosicao("Valor previsto", `${formatarMoeda(p.valor_previsto)} (${formatarPercentual(p.resultado_previsto_pct)})`, true);
    if (p.faixa_valor) {
      html += linhaPosicao("Sua posição na faixa",
        `${formatarMoeda(p.faixa_valor[0])} a ${formatarMoeda(p.faixa_valor[1])}`);
    }
  }
  document.getElementById("grade-posicao").innerHTML = html;
  document.getElementById("posicao-avisos").textContent = (d.avisos || []).join(" ");
}

function lerPosicaoDoFormulario() {
  const qtd = parseFloat(document.getElementById("campo-quantidade").value);
  const entrada = parseFloat(document.getElementById("campo-entrada").value);
  const corpo = {};
  if (Number.isFinite(qtd) && qtd > 0) corpo.quantidade = qtd;
  if (Number.isFinite(entrada) && entrada > 0) corpo.cotacao_entrada = entrada;
  return corpo;
}

async function enviarPosicao(evento) {
  if (evento) evento.preventDefault();
  const corpo = lerPosicaoDoFormulario();
  if (corpo.quantidade && !corpo.cotacao_entrada) {
    document.getElementById("posicao-avisos").textContent =
      "Informe a cotação de compra para calcular o resultado da posição.";
    return;
  }
  try {
    exibirPosicao(await analisarPosicao(corpo));
  } catch (erro) {
    document.getElementById("posicao-avisos").textContent = erro.message;
  }
}

function limparPosicao() {
  document.getElementById("campo-quantidade").value = "";
  document.getElementById("campo-entrada").value = "";
  enviarPosicao();
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
  document.getElementById("form-posicao").addEventListener("submit", enviarPosicao);
  document.getElementById("btn-limpar-posicao").addEventListener("click", limparPosicao);

  carregarTudo().catch(mostrarErro);
}

document.addEventListener("DOMContentLoaded", iniciar);