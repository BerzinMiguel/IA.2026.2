> Nota: este relatório é anterior à reorganização de pastas. Os caminhos citados
> mudaram: `Multistep.py` para `ia/multistep.py`, `Bases_para_Treinamento.py`
> para `ia/bases.py`, `Tratamento_Dados.py` para `ia/tratamento.py`, `ia_svr/`
> para `ia/svr/` e `executar_svr.py` para `scripts/treinar_svr.py`. As pendências
> listadas no fim (rotas HTTP, escolha do horizonte, calendário futuro e
> agendamento) estão atendidas em `backend/` e `ia/adaptador.py`. Artefatos
> `pipeline.joblib` gerados antes da mudança precisam ser treinados de novo,
> porque o joblib guarda o caminho antigo do módulo.

# Verificação da integração — 16/11/2026

## Código examinado e decisão

Histórico recente: `d5cb92f` (Multistep), `0200ec3` (preparador), `c637143`
(volatilidade), além do SVR original de Lays e do contrato mock em `front/js/api.js`.
O repositório possui uma implementação Multistep genérica; a integração a executa
para as três séries. Não existem três artefatos Multistep pré-treinados versionados.
As interfaces reais e o contrato de Miguel estão detalhados em README_LAYS.md.

Foram mantidos os métodos originais de Ryan, o ModeloSVR original de Lays e o
frontend. O caminho novo usa regressão equivalente em memória e treino expansivo
OOS, com um SVR por horizonte. Não foram executados commit, push ou merge.

## Ambiente utilizado

Python do `.venv/Scripts/python.exe`, com NumPy 2.5.5, pandas 2.3.3,
scikit-learn 1.9.1, openpyxl 3.1.5, requests 2.34.2, joblib 1.6.0 e tzdata 2026.6.
`python` global falhou ao importar sklearn (`ModuleNotFoundError`); o ambiente
virtual existente contém as dependências necessárias. Não foi necessário instalar
pacotes. `.venv/Scripts/python.exe -m pip check`: `No broken requirements found.`

## Testes efetivamente executados

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Resultado final: **9 testes, 12,207 segundos, OK**, sem falhas ou avisos na execução
final. Inclui dois testes originais e sete de integração: Excel → pipeline → JSON,
persistência, CLI com artefato, argumentos ausentes, alinhamento, erros de dados,
limites das recomendações, paridade numérica com Ryan e ausência de influência
de dados futuros nas entradas passadas e no ajuste do SVR.
`git diff --check` também passou. Testes sintéticos não são métricas financeiras.

## Execução com bases locais reais

Bases existentes: ação Petrobras com 1.711 linhas e dólar com 1.724 linhas,
ambas entre 02/01/2020 e 13/11/2026. Não havia arquivo de volatilidade.
Foi gerado `resultados/volatilidade.xlsx` com a função de Ryan, a partir dos
fechamentos locais da ação. Os dados não foram baixados novamente nem tiveram
sua origem/qualidade auditadas externamente.

Configuração: dimensão 12, H=2, mínimo de 60 observações e teste nas últimas 20%
das origens. Após remover a primeira volatilidade vazia e alinhar datas,
restaram **1.710 observações**. Treino e avaliação completos levaram **60,682 s**.
Último alvo do treino SVR: 17/07/2025. Primeira origem de teste: 18/07/2025.

| Horizonte | Treino SVR | Teste | MAE (R$) | RMSE (R$) | MAPE (%) |
|---|---:|---:|---:|---:|---:|
| 1 | 1318 | 330 | 3,550184 | 7,398597 | 7,140926 |
| 2 | 1317 | 330 | 3,854174 | 7,578708 | 7,899230 |

Os valores completos estão em `resultados/metricas_svr.json`; os erros individuais
em `resultados/avaliacao_svr.csv` e as entradas históricas em `previsoes_oos.csv`.
Também foi salvo `resultados/pipeline.joblib`. Esses arquivos permanecem ignorados
pelo Git conforme a configuração existente.

O carregamento real pela CLI também terminou com código 0:

```powershell
.venv/Scripts/python.exe executar_svr.py --carregar resultados/pipeline.joblib
```

No snapshot de 13/11/2026, preço observado da ação 45,2999992371:
SVR h=1 retornou 39,4868155200 (−12,833%, RETIRAR), h=2 retornou
37,9013605457 (−16,333%, RETIRAR). São resultados acadêmicos do código sobre
os arquivos locais, não recomendações reais. O erro medido é relevante; não
há evidência de que a regra gere rentabilidade. O SVR salvo permanece congelado
no corte de avaliação, conforme documentado.

## Reprodução do treino completo

```powershell
.venv/Scripts/python.exe -c "from Tratamento_Dados import gerar_planilha_volatilidade_diaria; gerar_planilha_volatilidade_diaria('dados/Ação_Petrobras_tratado.xlsx', 'resultados/volatilidade.xlsx')"
.venv/Scripts/python.exe executar_svr.py --dolar "dados/Dólar_tratado.xlsx" --bolsa "dados/Ação_Petrobras_tratado.xlsx" --volatilidade resultados/volatilidade.xlsx --saida resultados
```

## Arquivos alterados ou acrescentados

- `Multistep.py`: método em memória equivalente à regressão original.
- `ia_svr/integracao.py`: leitura, alinhamento, OOS, expurgo, treino, avaliação,
  persistência e resposta serializável para o backend.
- `ia_svr/__init__.py`: exporta PipelineIntegrado.
- `ia_svr/modelo.py`: valida limiar e calcula diferença relativa evitando o erro
  do quociente original nas fronteiras de ±2% cobertas pelo teste.
- `executar_svr.py`: CLI integrada com treino ou carregamento e tratamento de erros.
- `requirements-svr.txt`: requests para coleta/geração e tzdata no Windows.
- `tests/test_integracao.py`: testes integrados e temporais.
- `README_LAYS.md`, `README_Multistep.md`, `RELATORIO_INTEGRACAO.md`: contratos,
  critérios, execução e evidências.

## Pendências de integração externa

Sem bloqueio de dependências ou bases no `.venv` para a execução realizada.
Miguel precisa expor as rotas HTTP, selecionar o horizonte nas métricas/avaliação,
fornecer calendário futuro se quiser datas-alvo explícitas e programar a atualização
com novos dados. Sem calendário, `data_alvo=null`, sem inventar pregões.
A produção usa o snapshot salvo; novos dados exigem novo treino e substituição
da instância. É necessário confirmar a ação-alvo e manter a mesma definição de
volatilidade no backend. O frontend continua usando mocks, sem alterações.
