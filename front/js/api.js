/* =========================================================
   api.js — Comunicação com o backend
   ---------------------------------------------------------
   Enquanto USAR_MOCK = true, as funções devolvem dados
   falsos para a tela funcionar sem backend.
   Quem fizer o backend: implemente os endpoints abaixo,
   troque USAR_MOCK para false e ajuste API_URL.
   ========================================================= */

const API_URL = "http://localhost:8000/api";
const USAR_MOCK = true;

/* Requisição genérica: trata erro e converte para JSON */
async function requisitar(caminho, opcoes = {}) {
  const resposta = await fetch(`${API_URL}${caminho}`, {
    headers: { "Content-Type": "application/json" },
    ...opcoes,
  });
  if (!resposta.ok) {
    throw new Error(`Erro ${resposta.status} em ${caminho}`);
  }
  return resposta.json();
}

/* ---------------------------------------------------------
   GET /api/previsao/atual
   Retorna a previsão do dia (multistep + SVR).
   Formato esperado:
   {
     "data_atualizacao": "2026-11-16",
     "data_alvo": "2026-11-17",
     "indicadores": {
       "dolar":        { "atual": 5.31,  "previsto": 5.28 },
       "bolsa":        { "atual": 37.80, "previsto": 38.65 },
       "volatilidade": { "atual": 1.42,  "previsto": 1.35 }
     },
     "fechamento_previsto": 38.65,
     "recomendacao": "APLICAR",          // APLICAR | MANTER | RETIRAR
     "variacao_prevista_pct": 2.249,
     "aviso": "Demonstração acadêmica; ..."
   }
   --------------------------------------------------------- */
async function buscarPrevisaoAtual() {
  if (USAR_MOCK) return mockPrevisaoAtual();
  return requisitar("/previsao/atual");
}

/* ---------------------------------------------------------
   GET /api/historico?indicador=bolsa&dias=30
   indicador: "dolar" | "bolsa" | "volatilidade"
   Formato esperado: [ { "data": "2026-10-17", "valor": 37.12 }, ... ]
   (ordem cronológica crescente)
   --------------------------------------------------------- */
async function buscarHistorico(indicador, dias) {
  if (USAR_MOCK) return mockHistorico(indicador, dias);
  return requisitar(`/historico?indicador=${indicador}&dias=${dias}`);
}

/* ---------------------------------------------------------
   GET /api/recomendacoes?dias=30
   Histórico das recomendações salvas diariamente.
   Formato esperado:
   [ { "data": "2026-11-14", "fechamento_previsto": 37.9,
       "variacao_prevista_pct": 0.8, "recomendacao": "MANTER" }, ... ]
   --------------------------------------------------------- */
async function buscarRecomendacoes(dias = 30) {
  if (USAR_MOCK) return mockRecomendacoes(dias);
  return requisitar(`/recomendacoes?dias=${dias}`);
}

/* ---------------------------------------------------------
   GET /api/avaliacao
   Conteúdo do resultados/avaliacao_svr.csv em JSON.
   Formato esperado:
   [ { "data_alvo": "2026-10-01", "real": 37.1, "previsto": 36.9, "erro": 0.2 }, ... ]
   --------------------------------------------------------- */
async function buscarAvaliacao() {
  if (USAR_MOCK) return mockAvaliacao();
  return requisitar("/avaliacao");
}

/* ---------------------------------------------------------
   GET /api/metricas
   Conteúdo do resultados/metricas_svr.json.
   Formato esperado:
   { "amostras_treino": 400, "amostras_teste": 100,
     "MAE": 0.42, "RMSE": 0.57, "MAPE_pct": 1.13,
     "observacao": "..." }
   --------------------------------------------------------- */
async function buscarMetricas() {
  if (USAR_MOCK) return mockMetricas();
  return requisitar("/metricas");
}

/* ---------------------------------------------------------
   POST /api/atualizar
   Pede ao backend para coletar o fechamento do dia,
   retreinar e gerar nova previsão.
   Formato esperado: { "status": "ok", "data_atualizacao": "2026-11-16" }
   --------------------------------------------------------- */
async function solicitarAtualizacao() {
  if (USAR_MOCK) return { status: "ok", data_atualizacao: hojeISO() };
  return requisitar("/atualizar", { method: "POST" });
}


/* =========================================================
   DADOS FALSOS (MOCK) — apagar quando o backend estiver pronto
   ========================================================= */

function hojeISO(deslocamentoDias = 0) {
  const d = new Date();
  d.setDate(d.getDate() + deslocamentoDias);
  return d.toISOString().slice(0, 10);
}

function mockPrevisaoAtual() {
  return {
    data_atualizacao: hojeISO(),
    data_alvo: hojeISO(1),
    indicadores: {
      dolar: { atual: 5.31, previsto: 5.28 },
      bolsa: { atual: 37.8, previsto: 38.65 },
      volatilidade: { atual: 1.42, previsto: 1.35 },
    },
    fechamento_previsto: 38.65,
    recomendacao: "APLICAR",
    variacao_prevista_pct: 2.249,
    aviso: "Demonstração acadêmica; não usar para decisões financeiras reais.",
  };
}

function mockHistorico(indicador, dias) {
  const base = { dolar: 5.3, bolsa: 37, volatilidade: 1.4 }[indicador];
  const amplitude = { dolar: 0.08, bolsa: 1.6, volatilidade: 0.5 }[indicador];
  return Array.from({ length: dias }, (_, i) => ({
    data: hojeISO(i - dias + 1),
    valor: +(base + Math.sin(i / 5) * amplitude + (Math.random() - 0.5) * amplitude * 0.4).toFixed(3),
  }));
}

function mockRecomendacoes(dias) {
  const opcoes = ["APLICAR", "MANTER", "RETIRAR"];
  return Array.from({ length: dias }, (_, i) => {
    const variacao = +((Math.random() - 0.5) * 6).toFixed(2);
    return {
      data: hojeISO(-i),
      fechamento_previsto: +(37 + Math.random() * 2).toFixed(2),
      variacao_prevista_pct: variacao,
      recomendacao: variacao > 2 ? opcoes[0] : variacao < -2 ? opcoes[2] : opcoes[1],
    };
  });
}

function mockAvaliacao() {
  return Array.from({ length: 40 }, (_, i) => {
    const real = 37 + Math.sin(i / 4) * 1.5;
    const previsto = real + (Math.random() - 0.5) * 0.9;
    return {
      data_alvo: hojeISO(i - 40),
      real: +real.toFixed(3),
      previsto: +previsto.toFixed(3),
      erro: +(real - previsto).toFixed(3),
    };
  });
}

function mockMetricas() {
  return {
    amostras_treino: 400,
    amostras_teste: 100,
    MAE: 0.421,
    RMSE: 0.573,
    MAPE_pct: 1.13,
    observacao: "Avaliação cronológica com entradas reais, não previsões multistep.",
  };
}