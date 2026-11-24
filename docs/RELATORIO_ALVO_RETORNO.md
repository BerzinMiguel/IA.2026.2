# Correção do alvo do SVR: de nível de preço para variação

Trabalho feito sobre o commit `d060ce5` ("Ajusta preparacao de dados e integracao
SVR Multistep"). Branch: `feature/alvo-retorno`.

## 1. O problema encontrado

Depois do `d060ce5`, o pipeline rodava sem erro e os 31 testes passavam, mas a
qualidade caiu muito nos dados reais (referência 2026-11-16, horizonte 2):

| | antes (`a6b5b6d`) | depois (`d060ce5`) |
|---|---|---|
| previsão para 18/11 | 38,26 | 28,08 |
| variação prevista | −13,09% | −36,20% |
| MAE | 3,87 | 11,39 |
| RMSE | 7,59 | 13,79 |
| MAPE | 7,94% | 26,13% |

A busca em grade escolheu `C=0.01, gamma=1e-05, epsilon=0.01`, ou seja o menor C
e o menor gamma da grade. Sondando o modelo treinado com entradas muito
diferentes:

```
dolar=  3.00 : vol=0.0 -> 28.0850   vol=1.9 -> 28.0850   vol=10.0 -> 28.0850
dolar=  5.73 : vol=0.0 -> 28.0850   vol=1.9 -> 28.0850   vol=10.0 -> 28.0850
dolar= 50.00 : vol=0.0 -> 28.0845   vol=1.9 -> 28.0845   vol=10.0 -> 28.0845

previsoes no conjunto de teste: amplitude 0,000009   desvio-padrao 0,000002
(desvio-padrao do alvo real: 7,7763)
```

O SVR tinha virado uma **constante** de 28,085, praticamente a média dos alvos de
treino (28,25). Com `gamma=1e-05` sobre entradas normalizadas em [0,1], o kernel
RBF vale ≈0,99999 para qualquer par de pontos e a predição é só o termo de viés.
Como o preço atual era 44,02, isso aparecia como uma queda de 36% todo dia e a
recomendação era `retirar` com confiança 1,0.

## 2. A causa

A busca em grade não estava com defeito; ela expôs um alvo mal especificado.

O alvo era o **nível do preço** de uma série em tendência. No recorte usado, o
treino ficava entre R$ 14,30 e R$ 42,90 e o teste entre R$ 29,45 e R$ 59,68,
faixas que quase não se cruzam. A validação fica num patamar mais alto que o
treino, então qualquer modelo que de fato use as entradas extrapola e erra muito
na validação. O modelo mais achatado possível é o que minimiza o MSE de
validação, e a grade escolheu a constante por construção. O SVR com kernel RBF
não extrapola além da faixa de alvos vista no treino.

Isso já estava descrito como limite conhecido na seção 6 do
`scripts/demonstrar.py` antes deste trabalho. O `d060ce5` levou o efeito ao
extremo porque o split em três partes encurtou o treino (último alvo recuou de
2025-07-18 para 2024-03-22), afastando ainda mais a faixa de treino do preço
atual.

## 3. A baseline que faltava

Não havia critério de aceite no projeto. Medimos o modelo trivial de
persistência, "o preço em t+h é o preço de hoje", no mesmo recorte de teste
(330 amostras, 2025-07-21 a 2026-11-12, h=2):

| | MAE | RMSE | MAPE |
|---|---|---|---|
| **persistência (trivial)** | **0,858** | **1,208** | **2,06%** |
| SVR antes (`a6b5b6d`) | 3,872 | 7,589 | 7,94% |
| SVR depois (`d060ce5`) | 11,394 | 13,788 | 26,13% |

Nenhuma das duas versões batia o modelo trivial. Sem esse número, "melhor MSE"
era o modelo comparado contra si mesmo.

## 4. O que foi alterado

O SVR passou a treinar sobre **variação** em vez de nível de preço:

```
alvo_retorno = bolsa[t+h] / bolsa[t] - 1
```

e a previsão volta para reais como `bolsa[t] * (1 + variação)`. As métricas
continuam na unidade do preço, para poderem ser comparadas com a baseline e com
as versões anteriores.

**`ia/svr/modelo.py`**

- Constantes `ALVO_RETORNO` e `PRECO_ORIGEM`.
- `retorno_para_preco(preco_origem, retorno)`: a volta para reais.
- `prever_ativo` virou `prever_retorno` (variação) e `prever_preco` (variação +
  preço de origem para reais, com validação do preço).
- `avaliar_svr(..., base_preco=...)`: lê a saída do modelo como variação e
  avalia em reais. Cálculo dos erros extraído para `_erros`.
- `baseline_persistencia(teste)`: a referência trivial, no mesmo recorte.
- `ModeloSVR.treinar` grava `preco_origem` e `alvo_retorno`, treina sobre
  variação, avalia em reais e inclui a baseline nas métricas.

**`ia/svr/integracao.py`**

- `gerar_historico` grava `preco_origem` e `alvo_retorno` em cada linha.
- `treinar` passa `alvo=ALVO_RETORNO` e avalia com `base_preco=PRECO_ORIGEM`.
  Cada horizonte agora reporta `baseline_persistencia`.
- `prever_com_multistep_e_svr` recebe o preço de origem para a conversão.
- Versão do artefato 2 para 3. Um `pipeline.joblib` da versão 2 prevê nível;
  lido por este código, a saída seria interpretada como variação. A checagem
  recusa em vez de aceitar calado.

**`ia/adaptador.py`**

- `IA_FRACAO_VALIDACAO` e `IA_FRACAO_TESTE` (padrão 0.2 e 0.2, ou seja
  60/20/20). Para o 80/10/10, use 0.1 e 0.1. Entram na chave do cache.

**`scripts/demonstrar.py`**

- Etapa 2 descreve as duas entradas e o alvo de variação.
- Nova seção explicando a baseline como critério de aceite.
- Seção 4 imprime a comparação modelo contra baseline e o ganho em MAE.
- Seção 6 separa o limite resolvido do limite que permanece.

**`README.md`**: "consolida as três previsões" estava errado desde o `d060ce5`,
que tirou a bolsa das entradas do SVR. Corrigido.

Não foi alterado: a refatoração de helpers do `d060ce5`, a divisão 60/20/20 com
expurgo temporal, a maquinaria da busca em grade e a validação de artefato.

## 5. Resultado

Referência 2026-11-16, horizonte 2, mesmo recorte de teste:

| | nível (`d060ce5`) | variação (este trabalho) |
|---|---|---|
| previsão para 18/11 | 28,08 | 44,16 |
| variação prevista | −36,20% | +0,32% |
| recomendação | RETIRAR (conf. 1,0) | MANTER (conf. 0,08) |
| MAE | 11,394 | **0,855** |
| RMSE | 13,788 | **1,208** |
| MAPE | 26,13% | **2,058%** |
| parâmetros escolhidos | C=0,01 γ=1e−05 | C=0,01 γ=0,0001 |

O modelo deixou de ser constante e passou a responder às entradas. Os 31 testes
continuam passando.

Comparado à baseline, por horizonte:

| horizonte | modelo MAE | baseline MAE | ganho |
|---|---|---|---|
| 1 | 0,5558 | 0,5615 | +1,01% |
| 2 | 0,8545 | 0,8581 | +0,41% |

## 6. Limite que permanece

O ganho sobre a persistência é de cerca de 1%, ou seja o modelo **empata** com o
trivial. Dólar e volatilidade praticamente não carregam informação sobre a
variação da ação em um ou dois pregões, o que é o esperado para dados diários.
Os parâmetros escolhidos pela grade mudam muito conforme o recorte (de
`gamma=1e-04` a `gamma=10`), sinal de que a busca está ajustando ruído da
validação.

Esse é o resultado honesto: a cadeia funciona, está medida corretamente, e o
poder preditivo é baixo. É um resultado defensável e muito mais informativo que
um número bonito vindo de um modelo constante.

## 7. Dúvidas levantadas no grupo

**"Ele deve pegar a base desde o início, acho que está pegando um intervalo."**

Já pega a série inteira. A base alinhada vai de **2020-01-03 a 2026-11-16**
(1711 observações) e a primeira origem do histórico é **2020-03-30**, que é a
primeira possível depois das 60 observações de aquecimento
(`IA_MINIMO_TREINO`). O que confunde é o `-t2024-03-22` no nome do modelo: isso
é o **fim** do treino, não o início. `IA_MAX_OBS_TREINO` está em 0, ou seja sem
truncamento.

**"Ele devia fazer uma divisão de 80/10/10."**

Medido, nos três splits:

| split | h | treino até | amostras de teste | modelo MAE | baseline MAE | ganho |
|---|---|---|---|---|---|---|
| 60/20/20 | 1 | 2024-03-22 | 330 | 0,5558 | 0,5615 | +1,01% |
| 60/20/20 | 2 | 2024-03-22 | 330 | 0,8545 | 0,8581 | +0,41% |
| 80/10/10 | 1 | 2025-07-18 | 165 | 0,7571 | 0,7679 | +1,40% |
| 80/10/10 | 2 | 2025-07-18 | 165 | 1,1573 | 1,1543 | −0,26% |
| 70/15/15 | 1 | 2024-11-13 | 248 | 0,6469 | 0,6544 | +1,15% |
| 70/15/15 | 2 | 2024-11-13 | 248 | 0,9959 | 1,0035 | +0,76% |

O 80/10/10 treina com dados mais recentes, o que é a favor dele, mas o MAE
absoluto sobe porque o conjunto de teste também muda: fica com 165 amostras de
2026-03 a 2026-11, um período mais volátil. **Comparar MAE entre splits
diferentes é comparar recortes diferentes.** O que dá para comparar é o ganho
sobre a baseline no mesmo recorte, e aí o 80/10/10 fica pior em h=2 (−0,26%, o
modelo perde do trivial). O split agora é configurável por
`IA_FRACAO_VALIDACAO` e `IA_FRACAO_TESTE`, sem mexer em código.

**"E também tem a questão dos parâmetros."**

Procede, e agora faz sentido atacar. Antes, com alvo em nível, a grade escolhia
sempre o piso (`C=0,01`, `gamma=1e-05`) em qualquer configuração. Sobre variação
ela passa a escolher valores variados conforme o recorte, ou seja a busca voltou
a ter efeito. Esse é o pré-requisito para os itens 2 (lag por autocorrelação) e
3 (grade do SVR) do plano valerem a pena.

## 8. Próximos passos do plano

1. Item 2: lag por autocorrelação, comparando por MSE. Agora mede algo real.
2. Item 3: grade do SVR no Colab, sobre variação.
3. ~~Item 4~~: **feito**, ver seção 9.


## 9. Item 4: decisão com a posição do usuário

Implementado. O sinal de mercado continua global (uma `recomendacao` por
execução em `execucoes`), e a camada do usuário é aplicada na borda, em
`POST /api/decisao`, sem gravar nada. Assim duas pessoas veem enquadramentos
diferentes do mesmo dia sem duplicar execução nem criar estado por usuário.

**`ia/decisao.py`** (novo, sem dependência de backend ou de pandas):

| | alta | sem sinal | baixa |
|---|---|---|---|
| **sem posição** | APLICAR | MANTER | MANTER |
| **com posição** | APLICAR MAIS | MANTER | RETIRAR |

São as quatro classes pedidas pelo professor, e `RETIRAR` nunca aparece para
quem não tem posição.

O campo `sinal` viaja separado da recomendação porque `MANTER` sai por dois
motivos distintos: queda prevista para quem não tem posição, ou o modelo não
ter nada a dizer. `sem_sinal` é o caso em que a variação prevista não supera o
erro típico do modelo — hoje, previsão de +0,33% contra um MAE de 1,73%, ou
seja dentro do ruído. A resposta carrega `erro_modelo_pct`, `faixa_preco` e,
havendo posição, `faixa_valor`, para a tela mostrar a incerteza em vez de um
ponto seco.

O preço de entrada **não entra na decisão**, só no relato de resultado. Decidir
segurar porque está no prejuízo, ou vender porque está no lucro, é falácia do
custo irrecuperável; há teste garantindo que a recomendação não muda quando só
a cotação de entrada muda. Quando a saída é `RETIRAR`, vem `motivo_retirada`
(`realizar lucro` ou `limitar prejuízo`), que é relato, não critério.

**Demais arquivos:** `backend/routes/api.py` (rota `POST /api/decisao`),
`front/index.html`, `front/js/api.js`, `front/js/app.js`, `front/css/style.css`
(formulário de quantidade e cotação, card de veredito com a faixa de erro),
`docs/CONTRATO_API.md` e `tests/test_decisao.py` (10 testes, 12 subtestes,
incluindo as seis combinações da matriz).

Suíte completa: **41 testes passando**.

Exemplo real, com a previsão de 16/11 e 100 ações compradas a R$ 38,50:

```
recomendacao  : MANTER   [sem_sinal]
preco         : hoje 44,02  previsto 44,16  (+0,326%)
erro do modelo: +-0,76  (1,727%)   faixa 43,40 a 44,92
investido     : R$ 3.850,00
valor hoje    : R$ 4.402,00  (+14,34%)
valor previsto: R$ 4.416,34  (+14,71%)   ganho no periodo R$ +14,34
faixa da posicao: R$ 4.340,30 a R$ 4.492,38
aviso         : variacao prevista dentro do erro tipico do modelo
```

O ganho previsto (R$ 14,34) é menor que a faixa de erro (±R$ 76) — e é
exatamente isso que o `sem_sinal` comunica.
