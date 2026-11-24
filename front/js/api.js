/* =========================================================
   api.js — Comunicação com o backend
   ---------------------------------------------------------
   O backend (Flask) serve este front e a API na mesma origem:

       python run.py   ->   http://localhost:8000

   Abrindo o front por fora (Live Server, arquivo local), as
   chamadas vão para http://localhost:8000/api, e o backend
   libera CORS.

   USAR_MOCK = true volta aos dados falsos, úteis para mexer
   no layout sem subir o backend.
   ========================================================= */

const PORTA_BACKEND = 8000;
const MESMA_ORIGEM = location.protocol.startsWith("http") &&
  (location.port === String(PORTA_BACKEND) || location.port === "");
const API_URL = (MESMA_ORIGEM ? "" : `http://localhost:${PORTA_BACKEND}`) + "/api";
const USAR_MOCK = false;

/* Requisição genérica: trata erro e converte para JSON */
async function requisitar(caminho, opcoes = {}) {
  const resposta = await fetch(`${API_URL}${caminho}`, {
    headers: { "Content-Type": "application/json" },
    ...opcoes,
  });
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => ({}));
    throw new Error(corpo.erro || `Erro ${resposta.status} em ${caminho}`);
  }
  return resposta.json();
}

/* ---------------------------------------------------------
   GET /api/previsao/atual
   Previsão mais recente (multistep + SVR) já gravada pelo backend.
   {
     "data_atualizacao": "2026-11-13",
     "data_alvo": "2026-11-17",
     "indicadores": {
       "dolar":        { "atual": 5.31,  "previsto": 5.28 },
       "bolsa":        { "atual": 37.80, "previsto": 38.65 },
       "volatilidade": { "atual": 1.42,  "previsto": 1.35 }
     },
     "fechamento_previsto": 38.65,       // saída do SVR
     "recomendacao": "APLICAR",          // APLICAR | MANTER | RETIRAR
     "variacao_prevista_pct": 2.249,
     "confianca": 0.56,
     "versao_modelo": "multistep+svr-d12-h2-t2025-07-17",
     "aviso": "Protótipo acadêmico. ..."
   }
   404 enquanto nenhuma previsão foi gerada (rode POST /api/atualizar).
   --------------------------------------------------------- */
async function buscarPrevisaoAtual() {
  if (USAR_MOCK) return mockPrevisaoAtual();
  return requisitar("/previsao/atual");
}

/* ---------------------------------------------------------
   GET /api/historico?indicador=bolsa&dias=30
   indicador: "dolar" | "bolsa" | "volatilidade"
   [ { "data": "2026-10-17", "valor": 37.12 }, ... ]
   Ordem cronológica crescente; `dias` conta pregões com dado,
   não dias de calendário.
   --------------------------------------------------------- */
async function buscarHistorico(indicador, dias) {
  if (USAR_MOCK) return mockHistorico(indicador, dias);
  return requisitar(`/historico?indicador=${indicador}&dias=${dias}`);
}

/* ---------------------------------------------------------
   GET /api/recomendacoes?dias=30
   Recomendações gravadas, da mais recente para a mais antiga.
   [ { "data": "2026-11-13", "data_alvo": "2026-11-17",
       "fechamento_previsto": 37.9, "variacao_prevista_pct": 0.8,
       "recomendacao": "MANTER", "confianca": 0.2 }, ... ]
   --------------------------------------------------------- */
async function buscarRecomendacoes(dias = 30) {
  if (USAR_MOCK) return mockRecomendacoes(dias);
  return requisitar(`/recomendacoes?dias=${dias}`);
}

/* ---------------------------------------------------------
   GET /api/avaliacao
   Previsões passadas que já têm fechamento real (erro = real - previsto).
   [ { "data_referencia": "2026-09-29", "data_alvo": "2026-10-01",
       "real": 37.1, "previsto": 36.9, "erro": 0.2,
       "recomendacao": "aplicar" }, ... ]
   --------------------------------------------------------- */
async function buscarAvaliacao() {
  if (USAR_MOCK) return mockAvaliacao();
  return requisitar("/avaliacao");
}

/* ---------------------------------------------------------
   GET /api/metricas
   { "MAE": 0.42, "RMSE": 0.57, "MAPE_pct": 1.13,
     "acerto_direcao": 0.54, "n_avaliadas": 60,
     "amostras_treino": 1318, "amostras_teste": 330,
     "versao_modelo": "...", "observacao": "..." }
   MAE/RMSE/MAPE saem do histórico walk-forward gravado pelo
   backend; amostras_treino/teste vêm do treino do SVR e ficam
   nulas quando a IA simulada está ativa.
   --------------------------------------------------------- */
async function buscarMetricas() {
  if (USAR_MOCK) return mockMetricas();
  return requisitar("/metricas");
}

/* ---------------------------------------------------------
   POST /api/atualizar
   Roda o pipeline do dia: histórico -> multistep -> SVR ->
   recomendação -> gravação.
   { "status": "ok" | "ja_existia", "data_atualizacao": "2026-11-13",
     "recomendacao": "manter", "execucao_id": 61 }
   --------------------------------------------------------- */
/* POST /api/decisao
   Cruza a posição informada com a última previsão gravada.
   Corpo vazio = usuário sem posição. Nada é gravado no banco. */
async function analisarPosicao(posicao = {}) {
  return requisitar("/decisao", {
    method: "POST",
    body: JSON.stringify(posicao),
  });
}

/* `baixar: true` manda o backend buscar pregões novos nas fontes antes de
   rodar a IA. Sem isso ele só reprocessa o que já está no banco. */
async function solicitarAtualizacao(baixar = true) {
  if (USAR_MOCK) return { status: "ok", data_atualizacao: hojeISO() };
  return requisitar("/atualizar", {
    method: "POST",
    body: JSON.stringify({ baixar }),
  });
}


/* =========================================================
   DADOS FALSOS (MOCK) — só entram em cena com USAR_MOCK = true
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
