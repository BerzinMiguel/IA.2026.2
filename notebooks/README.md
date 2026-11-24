# Análise e ajuste de parâmetros

Notebooks dos itens 2 e 3 do trabalho. Eles seguem o exemplo da aula (*Series Temporais Exp 04*) e usam as nossas bases de `dados/` (dólar, Petrobras e volatilidade). Nenhum arquivo do projeto foi alterado.

| Notebook | Conteúdo | Colab |
|---|---|---|
| `01_analise_lags.ipynb` | ACF de cada série, modelo linear (`pinv`) com lags de 1 a 30, escolha do melhor lag pelo MSE de validação e comparação no teste | [abrir](https://colab.research.google.com/github/BerzinMiguel/IA.2026.2/blob/analise-e-ajuste-nos-parametros/notebooks/01_analise_lags.ipynb) |
| `02_ajuste_parametros_svr.ipynb` | Busca em grade de `gamma`, `epsilon` e `C` do SVR (mesma grade do exemplo), comparando com o `SVR()` sem seleção | [abrir](https://colab.research.google.com/github/BerzinMiguel/IA.2026.2/blob/analise-e-ajuste-nos-parametros/notebooks/02_ajuste_parametros_svr.ipynb) |

No Colab basta usar **Ambiente de execução → Executar tudo**. As planilhas são lidas direto do GitHub.

Divisão: 60% treino, 20% validação e 20% teste, em ordem cronológica. A normalização Min–Max usa só o treino.

## Resumo dos resultados (dados até 13/11/2026)

| série | melhor lag | gamma | epsilon | C | MSE teste SVR ajustado | MSE teste `SVR()` padrão | MSE teste ingênuo |
|---|---|---|---|---|---|---|---|
| Dólar | 1 | 0,01 | 0,01 | 100 | 0,00049 | 0,00061 | 0,00049 |
| Petrobras | 1 | 1 | 0,001 | 1 | 0,00332 | 0,10612 | 0,00065 |
| Volatilidade | 14 | 0,01 | 0,01 | 100 | **0,00123** | 0,00502 | 0,00215 |

MSE na escala normalizada. A explicação de cada resultado está na seção de conclusões de cada notebook.
