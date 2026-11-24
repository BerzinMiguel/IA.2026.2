# Contrato da API (front ↔ backend)

Base: `http://localhost:8000/api` (o backend também serve o front em `/`, então
a página usa a mesma origem e não precisa de CORS).

Convenções:

- Datas sempre `YYYY-MM-DD`.
- `erro = real - previsto`.
- Recomendação em **MAIÚSCULAS** nas rotas do front (`APLICAR | MANTER | RETIRAR`)
  e em minúsculas no banco e nas rotas detalhadas.
- `real` nulo significa que a data-alvo ainda não chegou (ou não houve pregão);
  `/api/avaliacao` já devolve só as linhas comparáveis.
- Erros: `{"erro": "..."}` com 400 (parâmetro inválido), 404 (sem dados ainda),
  409 (execução concorrente) ou 502 (saída da IA fora do contrato).

---

## GET /api/previsao/atual

Tela 1. Última execução gravada.

```json
{
  "data_atualizacao": "2026-11-13",
  "data_alvo": "2026-11-17",
  "indicadores": {
    "dolar":        { "atual": 5.31,  "previsto": 5.28 },
    "bolsa":        { "atual": 37.80, "previsto": 38.12 },
    "volatilidade": { "atual": 1.42,  "previsto": 1.35 }
  },
  "fechamento_previsto": 38.65,
  "recomendacao": "APLICAR",
  "variacao_prevista_pct": 2.249,
  "confianca": 0.562,
  "versao_modelo": "multistep+svr-d12-h2-t2025-07-17",
  "gerado_em": "2026-11-13 21:04:11",
  "aviso": "Protótipo acadêmico. Não constitui recomendação de investimento."
}
```

`indicadores[*].previsto` é a saída dos **multistep**; `fechamento_previsto` é a
saída do **SVR**; por isso os dois valores da bolsa são diferentes.

`404` enquanto nenhuma previsão foi gerada: rode `POST /api/atualizar`.

## POST /api/decisao

Tela 1. Cruza a posição informada pelo usuário com a última previsão gravada.
**Nada é gravado**: a previsão é do mercado e igual para todos; só o
enquadramento muda por usuário.

Corpo (todos opcionais). Sem posição informada, avalia como quem não investiu:

```json
{ "quantidade": 100, "cotacao_entrada": 38.50 }
```

`valor_investido` pode substituir `quantidade`, desde que venha com
`cotacao_entrada`.

```json
{
  "tem_posicao": true,
  "sinal": "sem_sinal",
  "recomendacao": "MANTER",
  "data_alvo": "2026-11-18",
  "preco_atual": 44.02,
  "preco_previsto": 44.1634,
  "variacao_prevista_pct": 0.326,
  "limiar_pct": 2.0,
  "erro_modelo": 0.7604,
  "erro_modelo_pct": 1.727,
  "faixa_preco": [43.403, 44.9238],
  "posicao": {
    "quantidade": 100.0,
    "cotacao_entrada": 38.5,
    "valor_investido": 3850.0,
    "valor_atual": 4402.0,
    "resultado_atual": 552.0,
    "resultado_atual_pct": 14.338,
    "valor_previsto": 4416.34,
    "resultado_previsto": 566.34,
    "resultado_previsto_pct": 14.71,
    "ganho_previsto_periodo": 14.34,
    "faixa_valor": [4340.3, 4492.38]
  },
  "avisos": ["..."],
  "versao_modelo": "multistep+svr-d12-h2-t2024-03-01",
  "data_atualizacao": "2026-11-16",
  "aviso": "Protótipo acadêmico. Não constitui recomendação de investimento."
}
```

`recomendacao` é uma de `APLICAR | APLICAR MAIS | MANTER | RETIRAR`, do
cruzamento entre `sinal` e `tem_posicao`:

| | alta | sem_sinal | baixa |
|---|---|---|---|
| **sem posição** | APLICAR | MANTER | MANTER |
| **com posição** | APLICAR MAIS | MANTER | RETIRAR |

Nunca sai `RETIRAR` para quem não tem posição.

`sinal` viaja separado porque `MANTER` aparece por dois motivos diferentes: o
modelo prever queda para quem não tem posição, ou o modelo não ter sinal
nenhum. `sem_sinal` significa que a variação prevista não supera o erro típico
do modelo (`erro_modelo_pct`), ou seja, está dentro do ruído.

`posicao` é `null` para quem não tem posição. Quando a recomendação é
`RETIRAR`, vem também `motivo_retirada`: `"realizar lucro"` ou
`"limitar prejuízo"`.

`400` com `{"erro": "..."}` para entrada inválida (quantidade negativa,
`quantidade` sem `cotacao_entrada`, valores não finitos). `404` enquanto
nenhuma previsão foi gerada.

## GET /api/historico?indicador=bolsa&dias=30

Tela 2. Série observada, em ordem crescente. `indicador` ∈ `dolar | bolsa |
volatilidade`. `dias` conta **pregões com dado**, não dias de calendário.

```json
[ { "data": "2026-10-17", "valor": 37.12 }, { "data": "2026-10-18", "valor": 37.4 } ]
```

## GET /api/recomendacoes?dias=30

Tela 2. Da mais recente para a mais antiga.

```json
[
  {
    "data": "2026-11-13",
    "data_alvo": "2026-11-17",
    "fechamento_previsto": 38.65,
    "variacao_prevista_pct": 2.249,
    "recomendacao": "APLICAR",
    "confianca": 0.562,
    "versao_modelo": "multistep+svr-d12-h2-t2025-07-17"
  }
]
```

## GET /api/avaliacao?indicador=bolsa

Telas 2 e 3. Previsões que já têm fechamento real, em ordem crescente de
data-alvo. Equivale ao `resultados/avaliacao_svr.csv`, mas montado a partir do
histórico walk-forward gravado dia a dia pelo backend.

```json
[
  {
    "data_referencia": "2026-09-29",
    "data_alvo": "2026-10-01",
    "real": 37.10,
    "previsto": 36.90,
    "erro": 0.20,
    "recomendacao": "manter"
  }
]
```

## GET /api/metricas?indicador=bolsa

Tela 3.

```json
{
  "indicador": "bolsa",
  "MAE": 0.42,
  "RMSE": 0.57,
  "MAPE_pct": 1.13,
  "acerto_direcao": 0.54,
  "n_avaliadas": 28,
  "amostras_treino": 1318,
  "amostras_teste": 330,
  "versao_modelo": "multistep+svr-d12-h2-t2025-07-17",
  "modelo": { "MAE": 3.55, "RMSE": 7.39, "MAPE_pct": 7.14,
              "ultimo_alvo_treino": "2025-07-17",
              "primeira_origem_teste": "2025-07-18" },
  "observacao": "..."
}
```

- `MAE`, `RMSE`, `MAPE_pct`, `acerto_direcao`: calculados sobre as previsões que
  o backend gravou e depois comparou com o fechamento real.
- `amostras_treino`, `amostras_teste` e `modelo`: vêm do treino do SVR. Ficam
  **nulos** com a IA simulada (`IA_MODE=mock`), e o front mostra `--`.

## POST /api/atualizar

Roda o pipeline do dia. Corpo opcional:
`{"data_referencia": "2026-11-13", "sobrescrever": true}`.

```json
{ "status": "ok", "data_referencia": "2026-11-13", "data_atualizacao": "2026-11-13",
  "execucao_id": 31, "recomendacao": "manter" }
```

`status` é `ok` ou `ja_existia` (a data já tinha execução e `sobrescrever` não
foi pedido). Saída da IA fora do contrato → `502` dizendo qual campo falhou.

### Corpo (todos opcionais)

| campo | efeito |
|---|---|
| `baixar` | busca pregões novos nas fontes (PTAX do Banco Central e fechamento da ação no Yahoo) **antes** de rodar a IA, e regrava as planilhas de `dados/`. É o que o botão Atualizar do front envia. |
| `sobrescrever` | recalcula mesmo que já exista execução para a data. |
| `data_referencia` | roda para uma data específica em vez do último pregão. |

Com `baixar`, a resposta traz também:

```json
"sincronizacao": {
  "ultima_data_antes": "2026-11-16",
  "ultima_data": "2026-11-23",
  "pregoes_novos": 4,
  "datas_novas": ["2026-11-17", "2026-11-18", "2026-11-19", "2026-11-23"],
  "ticker": "PETR4.SA"
}
```

`pregoes_novos: 0` significa que as fontes não tinham nada além do que já
estava no banco. Sem `baixar`, o campo não aparece.

A chamada com `baixar` leva alguns minutos: baixa as três séries e treina o
SVR para cada horizonte. `502` se as fontes externas não responderem.

## GET /api/health

```json
{ "status": "ok", "ia_mode": "real", "cotacoes": 5178, "ultima_execucao": "2026-11-13" }
```

---

## Rotas detalhadas (diagnóstico)

| Rota | Para quê |
|------|----------|
| `GET /api/visao-geral` | todos os passos previstos, entradas da decisão e confiança |
| `GET /api/desempenho` | métricas dos três indicadores, acerto das recomendações, série de erro |
| `GET /api/indicadores/{indicador}?inicio=&fim=` | série observada por intervalo de datas |

---

## Contrato interno: backend ↔ IA

O backend chama uma única função (`IA_MODULE`, padrão
`ia.adaptador:gerar_recomendacao`):

```python
gerar_recomendacao(historico: dict[str, pd.Series], data_referencia: str) -> dict
```

- `historico` tem `dolar`, `bolsa` e `volatilidade`, cada uma indexada por data e
  **somente com dados até `data_referencia`**. Essa garantia é do backend e é o
  que mantém o backfill sem vazamento.
- Retorno obrigatório: `versao_modelo`, `previsoes` (lista de `{data, valor}` por
  indicador, **data nunca nula**), `previsao_final` (`{data, valor}` do SVR),
  `recomendacao` (`aplicar|manter|retirar`), `confianca` (0–1 ou `null`) e
  `entradas` (livre; é gravada e reaparece em `/api/visao-geral`).
- `entradas.metricas_modelo` alimenta `amostras_treino`/`amostras_teste` em
  `/api/metricas`.
- Validação em `backend/services/ia.py`; esqueleto mínimo em `ia/exemplo.py`.
