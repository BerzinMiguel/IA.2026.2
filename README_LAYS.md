# Integração Lays: Multistep → SVR

Protótipo acadêmico. A integração usa o MQO direto de Ryan para dólar, ação
(`bolsa`) e volatilidade e um SVR RBF de Lays por horizonte. Não altera o frontend.

## Instalação e execução

Na raiz, Python 3.10+:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-svr.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Forneça as bases tratadas de dólar e ação com `Data`, `Valor` e a volatilidade
com `Data`, `Volatilidade_Diaria` (também aceita `Valor`). A função de Ryan
já existe e calcula `abs(log(preco_t/preco_t-1))*100`, sem anualização.
Não se trata de índice VIX ou desvio padrão móvel. A volatilidade pode ser zero.
Escolha e mantenha a mesma ação e definição em treino e produção.

```powershell
.venv/Scripts/python.exe -c "from Tratamento_Dados import gerar_planilha_volatilidade_diaria; gerar_planilha_volatilidade_diaria('dados/Ação_Petrobras_tratado.xlsx', 'dados/volatilidade.xlsx')"
.venv/Scripts/python.exe executar_svr.py --dolar "dados/Dólar_tratado.xlsx" --bolsa "dados/Ação_Petrobras_tratado.xlsx" --volatilidade dados/volatilidade.xlsx --horizonte 2 --saida resultados
.venv/Scripts/python.exe executar_svr.py --carregar resultados/pipeline.joblib
```

A CLI termina com código 2 em erros de dados/configuração. Não baixa dados.
Dependências ausentes na importação exigem instalar os requirements no mesmo Python.
Os formatos comuns são Excel/CSV/TSV/JSON, via `PreparadorBases._ler_planilha`;
formatos opcionais desse leitor (Parquet, XLS antigo etc.) exigem seus próprios engines.

## Contrato para Miguel

Treine fora da requisição HTTP; carregue uma vez no backend:

```python
from ia_svr import PipelineIntegrado

pipeline = PipelineIntegrado(dimensao=12, horizonte=2, minimo_treino=60)
metricas = pipeline.treinar(
    'dados/Dólar_tratado.xlsx', 'dados/Ação_Petrobras_tratado.xlsx',
    'dados/volatilidade.xlsx', pasta_saida='resultados')

# Após reiniciar o backend:
pipeline = PipelineIntegrado.carregar('resultados/pipeline.joblib')
resposta = pipeline.prever()
# Opcional: pipeline.prever(datas_alvo=['AAAA-MM-DD', 'AAAA-MM-DD'])
# Forneça as H datas reais futuras do calendário comum escolhido.
```

`resposta` é um dicionário JSON serializável (sem NaN), com:

- `data_atualizacao`: último fechamento comum utilizado, não o relógio do servidor;
- `data_alvo`, `horizonte`, `indicadores`, `fechamento_previsto`, `recomendacao`,
  `variacao_prevista_pct`, `aviso`: resultado de h=1, compatível com o contrato atual;
- `previsoes`: lista com esses campos para todos os horizontes;
- `avisos`: alinhamento, datas não fornecidas e eventuais indicadores MQO negativos;
- `criterio_horizonte`: observações nas datas comuns às três séries.

Sem calendário explícito, `data_alvo` é `None` (JSON `null`): não inventamos datas
nem presumimos que dia útil seja pregão. Datas fornecidas devem ser diárias,
estritamente crescentes, futuras e em quantidade H. Cabe ao backend validar
que correspondem ao calendário comum dos provedores. Todos os indicadores de h
preveem o mesmo alvo; o SVR de h prevê a ação nessa mesma data, sem deslocar h+1.
A recomendação compara o fechamento SVR com o último preço **observado** da ação,
não com o preço Multistep previsto.


Para as rotas atuais do frontend, `/api/metricas` deve devolver
`pipeline.metricas["1"]`; `/api/avaliacao` deve filtrar `pipeline.avaliacao`
por `horizonte == 1`, ordenando `data_alvo` e convertendo datas para ISO.
Assim não se misturam previsões de horizontes diferentes no mesmo gráfico.
Outros horizontes podem ser selecionados por parâmetro no backend.

O artefato guarda modelos, configuração, histórico observado, métricas e avaliação.
Só carregue joblib de origem confiável. Não aceita o antigo `modelo_svr.joblib`.
Inferência usa o snapshot salvo: para novas observações execute novamente `treinar`
e substitua a instância no backend depois da conclusão. O método não oferece atualização
incremental. `ValueError`, `FileNotFoundError` e `RuntimeError` devem virar erros
controlados na API; nunca substitua falhas por previsões fictícias.

## Separação temporal e avaliação

1. Datas são ordenadas e unidas por interseção, sem interpolação ou preenchimento.
   Duplicatas, preços inválidos, infinitos e datas inválidas são rejeitados.
   Apenas a primeira volatilidade vazia, produzida pelo gerador, é removida com aviso.
2. A partir de `minimo_treino`, cada origem histórica ajusta os três Multisteps
   somente no prefixo disponível até ela. A escala Min-Max também usa esse prefixo.
   O alvo real só é associado depois da previsão (janela expansiva fora da amostra).
3. Os últimos 20% das origens são teste. Para cada horizonte, o treino do SVR
   exclui todas as linhas cujo alvo é igual ou posterior à primeira origem de teste.
   StandardScaler e SVR são ajustados apenas no restante. Exigidos ao menos dez
   exemplos de treino e dois de teste por horizonte após o expurgo.
4. Avaliação usa SVRs congelados. Multisteps continuam em janela expansiva nas
   origens de teste: observações anteriores já disponíveis são permitidas.
   O pipeline salvo mantém esses SVRs, sem retreinar com os alvos de teste.

Arquivos em `--saida`: `pipeline.joblib`, `previsoes_oos.csv`,
`avaliacao_svr.csv` (origem, alvo, horizonte, real, previsto, erro),
`metricas_svr.json` (MAE, RMSE, MAPE e limites temporais por horizonte).
Métricas são calculadas na execução, nunca predefinidas. O treino expansivo pode
ser custoso em bases longas. Não há otimização de hiperparâmetros no teste.

## Critérios acadêmicos da recomendação

`variacao = (fechamento_previsto - preco_atual) / preco_atual`.
Limiar padrão 0,02: acima de +2% → **APLICAR**; abaixo de −2% → **RETIRAR**;
intervalo fechado [−2%, +2%] → **MANTER**. A decisão usa o valor sem arredondamento;
o percentual retornado tem três casas. Limiar configurável, finito e não negativo.
Não considera custos, risco, dividendos ou adequação do investidor. É uma regra
acadêmica, não uma estratégia validada nem aconselhamento financeiro.

## Relação com o código existente

O commit Ryan `d5cb92f` introduziu uma classe genérica, não três modelos salvos:
`Multistep.Modelo_multistep(treino, validacao, teste, coluna_treino,
coluna_validacao, coluna_teste, dimensao, horizonte)` retorna um array NumPy
`[t+1,...,t+H]` na escala original, sem datas. Os seletores são nomes ou índices
baseados em zero. `normalizar_bases` ajusta a escala no treino, grava Excel;
`prever_horizonte` ajusta `pinv(X) @ y` no treino e usa as três partes como histórico
recente. A previsão é posterior ao último teste, não uma avaliação histórica.
Esse caminho depende de pandas, NumPy e openpyxl; a classe não persiste coeficientes.

A integração acrescenta `Multistep.prever_serie(treino, historico, dimensao,
horizonte)`, matematicamente equivalente, em memória e sem arquivos intermediários.
Um teste compara ambos os caminhos. Em cada origem, treino e histórico recebem
o mesmo prefixo observado. Bases X/Y/Z já separadas devem ser reconstruídas em
ordem cronológica por série, sem sobreposição, antes de entrar na integração;
não forneça planilhas MinMax como se fossem preços originais.

`ModeloSVR` e `juntar_series` continuam disponíveis para compatibilidade com a
experiência original (indicadores observados em t → ação t+1). O treino integrado
não usa esse caminho; reutiliza a configuração do pipeline SVR. O artefato antigo
não é compatível com o treino de previsões e deve ser gerado novamente.
Os commits `c637143` e `0200ec3` fornecem o gerador de volatilidade e o preparador
de bases, respectivamente. O frontend permanece com seus mocks originais;
rotas HTTP, autenticação e agendamento ficam sob responsabilidade do backend.

## Verificação

`tests/test_integracao.py` cobre persistência, JSON, paridade com Ryan, imutabilidade
das previsões passadas quando o futuro muda, invariância do SVR a mudanças no teste,
expurgo temporal, datas, entradas inválidas, bases ausentes e volatilidade zero.
São dados sintéticos identificados como tal; não são evidência de desempenho real.
Veja `RELATORIO_INTEGRACAO.md` para os resultados efetivamente executados.
