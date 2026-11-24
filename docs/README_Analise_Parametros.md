# Análise e ajuste de parâmetros (itens 2 e 3)

Este documento descreve o que foi feito nos itens 2 e 3 do trabalho:

- **Item 2**: analisar a autocorrelação das nossas bases, escolher o melhor lag e comparar os resultados pelo MSE.
- **Item 3**: encontrar a melhor combinação de parâmetros do SVR, seguindo o exemplo do professor.

As duas análises foram feitas em notebooks do Colab, com base no exemplo da aula (*Series Temporais Exp 04*) e nas planilhas já versionadas em `dados/`.

## O que foi adicionado

| Arquivo | Conteúdo |
|---|---|
| `notebooks/01_analise_lags.ipynb` | Item 2: ACF, escolha do lag e comparação pelo MSE |
| `notebooks/02_ajuste_parametros_svr.ipynb` | Item 3: busca em grade dos parâmetros do SVR |
| `notebooks/README.md` | Links para abrir no Colab e resumo dos resultados |
| `docs/README_Analise_Parametros.md` | Este documento |

**Nenhum arquivo existente foi alterado.** Os notebooks leem as planilhas e fazem os cálculos por conta própria; `ia/`, `backend/`, `front/` e `scripts/` continuam iguais.

## Dados e divisão

| Base | Arquivo | Coluna | Dias |
|---|---|---|---|
| Dólar (PTAX) | `dados/Dolar_tratado.xlsx` | `Valor` | 1.724 |
| Petrobras (PETR4) | `dados/Petrobras_tratado.xlsx` | `Valor` | 1.711 |
| Volatilidade diária | `dados/volatilidade.xlsx` | `Volatilidade_Diaria` | 1.710 |

O período vai de 02/01/2020 a 13/11/2026. Como no exemplo do professor:

- a divisão é **60% treino, 20% validação e 20% teste**, em ordem cronológica, sem embaralhar;
- a normalização Min–Max usa o mínimo e o máximo **somente do treino**;
- a validação serve para escolher lag e parâmetros, e o teste só confirma o resultado no final;
- todos os MSE estão na escala normalizada [0, 1] do treino.

## Item 2: autocorrelação e escolha do lag

### Como foi feito

1. Gráfico da autocorrelação (ACF) de cada série até 40 lags, com a mesma função `acf_plot` do exemplo. Para dólar e Petrobras também foi feita a ACF da variação diária (diferença entre um dia e o anterior).
2. Para cada lag de 1 a 30, ajuste do modelo linear do exemplo, `coefs = pinv(train) · trainTarget`, com coluna de intercepto, e cálculo do MSE na validação.
3. Escolha do lag com menor MSE de validação e cálculo do MSE desse modelo no teste.
4. Comparação no teste com duas referências:
   - o **lag 12**, usado hoje no pipeline (`IA_DIMENSAO`);
   - o **modelo ingênuo**, que prevê que amanhã será igual a hoje.

O exemplo usa `stepahead = 1`. Também foi testado `stepahead = 2` (2 dias à frente), que é o horizonte do nosso pipeline.

### Correção em relação ao exemplo

No código original, a coluna de intercepto da validação é criada com `np.zeros_like`, enquanto a do treino e a do teste usam `np.ones_like`. Com zeros, o intercepto some das previsões de validação, e isso pode levar à escolha do lag errado. Nos notebooks, **as três bases usam uns**. Essa correção está explicada no início do notebook 01.

### Resultados

**Autocorrelação**

- **Dólar e Petrobras**: a ACF é muito alta e cai devagar (lag 1 ≈ 0,99; lag 39 ≈ 0,60 no dólar e 0,79 na Petrobras), e todos os lags passam do limite de significância. Isso acontece porque o preço de hoje fica muito perto do de ontem. Na variação diária, só alguns lags isolados passam do limite, e por pouco.
- **Volatilidade**: a ACF começa em ≈ 0,31 e cai aos poucos (≈ 0,10 no lag 10). Dias agitados vêm em sequência, então vários dias passados trazem informação.

**MSE**

| Série | stepahead | Melhor lag | MSE validação | MSE teste | MSE teste (lag 12) | MSE teste ingênuo |
|---|---|---|---|---|---|---|
| Dólar | 1 | **1** | 0,000486 | 0,000486 | 0,000503 | 0,000490 |
| Dólar | 2 | 1 | 0,001038 | 0,000873 | 0,000881 | 0,000887 |
| Petrobras | 1 | **1** | 0,000389 | 0,000660 | 0,000651 | 0,000652 |
| Petrobras | 2 | 17 | 0,000816 | 0,001395 | 0,001409 | 0,001411 |
| Volatilidade | 1 | **14** | 0,001316 | 0,001308 | 0,001322 | 0,002150 |
| Volatilidade | 2 | 13 | 0,001374 | 0,001355 | 0,001369 | 0,002479 |

### Conclusões do item 2

- **Volatilidade** é a série em que os lags realmente ajudam: com lag 14, o erro no teste fica cerca de **40% menor** que o do modelo ingênuo.
- **Dólar e Petrobras** ficam no mesmo nível do modelo ingênuo. É o comportamento esperado para preços, em que a melhor previsão é o último valor. O lag 17 da Petrobras com `stepahead = 2` ganha na validação por muito pouco e não melhora o teste.
- O **lag 12** do pipeline dá resultados praticamente iguais aos do melhor lag, com diferenças abaixo de 2%.
- **Lags usados no item 3:** dólar = 1, Petrobras = 1, volatilidade = 14.

## Item 3: ajuste dos parâmetros do SVR

### Como foi feito

O procedimento é a segunda parte do exemplo do professor, repetida para cada série:

- **entradas**: os últimos `dimension` valores da série normalizada, com `dimension` igual ao melhor lag do item 2;
- **saída**: o valor do dia seguinte (`stepahead = 1`);
- **busca em grade** com as mesmas faixas do exemplo, num total de 120 combinações por série, cada uma treinada no treino e avaliada pelo MSE na validação:
  - `gamma` = 10⁻⁵, 10⁻⁴, …, 10² (8 valores)
  - `epsilon` = 10⁻⁴, 10⁻³, 10⁻² (3 valores)
  - `C` = 10⁻², 10⁻¹, …, 10² (5 valores)
- o melhor modelo (`SVR_Best`) é avaliado no teste e comparado com:
  - o `SVR()` sem seleção de parâmetros (`SVR_No_Selection`, padrão do sklearn), como no exemplo;
  - o modelo linear do item 2;
  - o modelo ingênuo.

O notebook também mostra as 5 melhores combinações de cada série, um mapa de calor do MSE de validação (`gamma` × `C`) e o gráfico do teste no mesmo formato do exemplo.

### Resultados

**Melhores parâmetros (menor MSE de validação)**

| Série | dimension | gamma | epsilon | C | MSE validação |
|---|---|---|---|---|---|
| Dólar | 1 | 0,01 | 0,01 | 100 | 0,000485 |
| Petrobras | 1 | 1 | 0,001 | 1 | 0,000381 |
| Volatilidade | 14 | 0,01 | 0,01 | 100 | 0,001199 |

**Comparação no teste (MSE)**

| Série | SVR_Best | SVR_No_Selection | Linear | Ingênuo |
|---|---|---|---|---|
| Dólar | 0,000488 | 0,000614 | 0,000486 | 0,000490 |
| Petrobras | 0,003317 | 0,106115 | 0,000660 | 0,000652 |
| Volatilidade | **0,001230** | 0,005021 | 0,001308 | 0,002150 |

### Conclusões do item 3

- **Ajustar os parâmetros vale a pena.** Nas três séries, o SVR ajustado erra bem menos que o `SVR()` padrão: cerca de 20% menos no dólar, 4 vezes menos na volatilidade e 32 vezes menos na Petrobras.
- **Volatilidade**: o SVR ajustado é o **melhor modelo** no teste, ganhando do linear e do ingênuo.
- **Dólar**: o SVR ajustado empata com o linear e com o ingênuo.
- **Petrobras**: mesmo com o melhor MSE de validação, o SVR erra **5 vezes mais** que o linear no teste. O motivo é que **33% dos dias do teste ficam acima do maior preço do treino**, chegando a 1,53 na escala normalizada. Com kernel RBF, o SVR não prevê valores fora da faixa que viu no treino, e a previsão fica "presa" perto do teto. É o mesmo problema descrito em "Limite conhecido do modelo" no `README.md` principal.

## Pontos para o relatório e próximos passos

- Para a Petrobras, vale testar o SVR com a **variação diária** como entrada e saída, em vez do preço, ou com **kernel linear**. Assim o modelo deixa de depender da faixa de preços do treino.
- O artigo de referência (Alves et al., 2022, *Learning and Nonlinear Models*, v. 20) usa uma grade mais larga (`C` até 10⁴, `gamma` até 10³, `epsilon` de 10⁻⁸ a 10⁻²) e escolhe os parâmetros com PSO em vez de busca em grade. Aqui foi usada a grade do exemplo da aula; ampliar a grade é uma extensão possível.
- Os parâmetros encontrados **ainda não foram aplicados** ao pipeline (`ia/svr/modelo.py` e `IA_DIMENSAO`). Essa decisão fica com os responsáveis por essas partes.

## Como rodar

**No Colab:** abra os links em `notebooks/README.md` e use **Ambiente de execução → Executar tudo**. As planilhas são lidas direto do GitHub. Rode o 01 antes do 02: o 02 usa os lags encontrados no 01, que já estão escritos na variável `MELHOR_LAG`.

**Localmente**, a partir da raiz do repositório:

```bash
pip install -r requirements.txt matplotlib jupyter
jupyter notebook notebooks/
```

Cada notebook leva menos de 1 minuto para rodar.
