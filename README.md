# IA 2026.2 — Previsão de fechamento e recomendação de investimento

Protótipo acadêmico que, a cada pregão, prevê **dólar**, **bolsa** (ação) e
**volatilidade** com três modelos multistep, consolida as três previsões num
**SVR** que estima o fechamento futuro da ação, e transforma isso em uma
recomendação: **aplicar**, **manter** ou **retirar**. Tudo fica gravado para
comparar previsão com o que realmente aconteceu.

> Resultado acadêmico. Erro medido não é rentabilidade; nada aqui é recomendação
> de investimento.

## Rodar em quatro comandos

```bash
pip install -r requirements.txt
python scripts/importar_dados.py --exemplo      # ou com as planilhas reais (abaixo)
python scripts/atualizar.py --backfill 30       # gera o histórico das telas 2 e 3
python run.py                                   # http://localhost:8000
```

O `run.py` serve a API **e** o dashboard na mesma porta: abra
`http://localhost:8000` e o front já estará falando com o backend.
Para checar só a API: `http://localhost:8000/api/health`.

Com as planilhas do tratamento de dados (CSV ou XLSX, formato BR ou ISO):

```bash
python scripts/importar_dados.py \
  --dolar dados/Dólar_tratado.xlsx \
  --bolsa "dados/Ação_Petrobras_tratado.xlsx" \
  --volatilidade resultados/volatilidade.xlsx     # se omitir, calcula da bolsa
```

Testes: `pytest -q` (backend, IA e integração; o do adaptador treina o modelo
de verdade em séries curtas).

## Fluxo diário

Depois do fechamento (ex.: cron `30 18 * * 1-5`):

```bash
python scripts/importar_dados.py --dolar ... --bolsa ...   # dados novos
python scripts/atualizar.py                                 # IA + gravação
```

1. **Dados**: séries atualizadas entram na tabela `cotacoes`.
2. **Multistep**: os três indicadores são previstos para os próximos passos.
3. **SVR**: recebe as previsões multistep e estima o fechamento futuro da ação.
4. **Decisão**: variação prevista acima de +2% vira aplicar; abaixo de -2%,
   retirar; entre os dois, manter.
5. **Histórico**: previsão, valores usados e recomendação ficam gravados; no dia
   seguinte o backend compara com o fechamento real.

O backfill é **walk-forward**: a execução do dia 10 só enxerga dados até o dia 10.
Sem isso, as métricas das telas 2 e 3 não teriam valor.

## Estrutura

```
backend/            API Flask + histórico local (SQLite)
  routes/api.py       endpoints consumidos pelo front
  services/dados.py   importação das planilhas, volatilidade, leitura sem vazamento
  services/ia.py      contrato com a IA, validação e IA simulada
  services/pipeline.py execução diária e backfill walk-forward
  services/metricas.py previsto x real, MAE/RMSE/MAPE, acerto de direção
  db.py               schema (cotacoes, execucoes, previsoes)
ia/                 inteligência
  tratamento.py       coleta e tratamento das séries, volatilidade diária
  bases.py            divisão temporal e normalização Min-Max
  multistep.py        previsão multistep por mínimos quadrados
  svr/                SVR, regra de decisão e pipeline integrado multistep -> SVR
  adaptador.py        ponte: gerar_recomendacao() no contrato do backend
  exemplo.py          esqueleto mínimo do contrato, para consulta
front/              dashboard (HTML/CSS/JS sem framework), servido pelo backend
scripts/            importar_dados.py, atualizar.py, treinar_svr.py
tests/              pytest (backend, IA e integração)
docs/               contrato da API e documentação de cada parte
dados/              planilhas tratadas e banco local (ignorado pelo Git)
resultados/         métricas, avaliação e pipeline.joblib (ignorado pelo Git)
```

As duas últimas pastas são criadas na primeira execução; nada de dado entra no
repositório.

## Modo da IA

| Variável     | Valor                               | Efeito                                   |
|--------------|-------------------------------------|------------------------------------------|
| `IA_MODE`    | `real` (padrão)                     | usa `ia/adaptador.py` (multistep + SVR)  |
| `IA_MODE`    | `mock`                              | IA simulada, mesmo contrato, sem treino  |
| `IA_MODULE`  | `ia.adaptador:gerar_recomendacao`   | função chamada no modo real              |
| `PORT`       | `8000`                              | porta da API e do front                  |

Ajustes do modelo (`IA_DIMENSAO`, `IA_HORIZONTE`, `IA_LIMIAR`, `IA_ARTEFATO`,
`IA_MAX_OBS_TREINO`, `IA_HORIZONTE_DECISAO`) estão documentados no topo de
`ia/adaptador.py`.

O modo `mock` existe para mexer no front sem esperar treino; ele segue o mesmo
contrato e o mesmo limiar de 2%, mas **não tem valor preditivo**.

### Treino

Por padrão o processo treina o SVR com o histórico disponível até a data de
referência e reaproveita esse modelo enquanto avança no tempo (nunca ao voltar).
Para congelar um modelo e não treinar a cada execução:

```bash
python scripts/treinar_svr.py --dolar ... --bolsa ... --volatilidade ... --saida resultados
IA_ARTEFATO=resultados/pipeline.joblib python scripts/atualizar.py
```

O backend recusa um artefato treinado com dados posteriores à data pedida, porque
isso vazaria o futuro na avaliação.

## API

Contrato completo em [docs/CONTRATO_API.md](docs/CONTRATO_API.md).

| Tela | Rota | Retorna |
|------|------|---------|
| 1. Dashboard | `GET /api/previsao/atual` | recomendação, fechamento previsto, os três indicadores |
| 2. Histórico | `GET /api/historico?indicador=bolsa&dias=30` | série observada |
| 2. Histórico | `GET /api/recomendacoes?dias=30` | recomendações passadas |
| 2 e 3 | `GET /api/avaliacao` | previsto x real, com erro |
| 3. Desempenho | `GET /api/metricas` | MAE, RMSE, MAPE e amostras do treino |
| - | `POST /api/atualizar` | roda o pipeline do dia |
| - | `GET /api/health` | status, modo da IA, última execução |

Rotas detalhadas para diagnóstico: `/api/visao-geral`, `/api/desempenho`,
`/api/indicadores/{dolar\|bolsa\|volatilidade}`.

## Divisão do trabalho

| Parte | Responsável | Onde está |
|-------|-------------|-----------|
| Dados, volatilidade e multistep | Ryan | `ia/tratamento.py`, `ia/bases.py`, `ia/multistep.py` |
| SVR, decisão e pipeline integrado | Lays | `ia/svr/` |
| Backend, histórico e integração | Miguel | `backend/`, `ia/adaptador.py`, `scripts/` |
| Front-end e visualização | Isabella | `front/` |

## Tempo de execução

Medido nesta máquina, com a série de exemplo (1.792 pregões):

| Operação | Tempo |
|----------|-------|
| `scripts/atualizar.py --backfill 30` (treino + 30 execuções) | ~3 min 40 s |
| Execuções seguintes no mesmo processo | segundos (modelo em cache) |
| `pytest -q` (inclui treino em séries curtas) | ~1 min 40 s |

Quase todo o tempo é o treino do SVR, que percorre todas as origens da série.
Na prática, o primeiro clique em "Atualizar" no dashboard treina o modelo e só
responde no fim. Para evitar isso, rode `scripts/atualizar.py` antes, congele um
modelo com `IA_ARTEFATO`, ou limite o treino com `IA_MAX_OBS_TREINO=300`, que
usa só as 300 observações mais recentes e responde em poucos segundos.

## Limite conhecido do modelo

O SVR é treinado para prever o nível do preço e, com kernel RBF, não extrapola acima da faixa que viu no treino: quando o preço sobe para um patamar
novo, a previsão fica presa perto da média do treino e a recomendação vira
`retirar` de forma sistemática.

Isso aparece nos dois conjuntos de dados:

- `docs/RELATORIO_INTEGRACAO.md`, com dados reais da Petrobras: preço observado
  45,30, previsto 39,49 (h=1) e 37,90 (h=2), ambos `RETIRAR`.
- Série de exemplo deste repositório, que dobra de nível ao longo do período:
  preço 46,35, previsto 19,87, MAPE de 52% e acerto de direção de 43%.

O SVR recebe as mesmas entradas com que foi treinado, então o problema está no
espaço em que o modelo aprende, não na ligação entre as partes. O caminho usual
é treinar sobre retorno (`preço_futuro / preço_atual - 1`) em vez do nível, ou
renormalizar cada janela pelo último fechamento. Até lá, as telas 2 e 3 mostram
o tamanho do erro.

## Decisões de integração

- **Volatilidade**: é sempre `|ln(Pt/Pt-1)| * 100` (definição de
  `ia/tratamento.py`). O backend calcula igual quando a planilha não é fornecida.
- **Datas-alvo**: o adaptador usa os próximos dias úteis; feriados da B3 não são
  considerados. Previsão que cai em feriado fica sem fechamento real e é
  ignorada nas métricas, em vez de comparada com o dia errado.
- **Erro**: em toda a API, `erro = real - previsto`.
- **Confiança**: distância relativa ao limiar (1.0 = variação de duas vezes o
  limiar), e não uma probabilidade.
- **Horizonte da decisão**: por padrão o último (`IA_HORIZONTE`, hoje 2 passos).
