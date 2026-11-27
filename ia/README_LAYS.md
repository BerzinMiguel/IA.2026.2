# Entrega Lays — SVR e decisão (protótipo acadêmico)

## Objetivo
Treinar um SVR com séries históricas de dólar, ação e volatilidade para prever o próximo fechamento da ação. A função `recomendar` classifica a variação prevista em APLICAR, MANTER ou RETIRAR, apenas como simulação acadêmica.

## Como executar
Na raiz do repositório, criar ambiente virtual e instalar `requirements-svr.txt`. Gerar previamente três planilhas tratadas com as colunas `Data` e `Valor` (uma por indicador), e executar:

```bash
python executar_svr.py --dolar dados/D_lar_tratado.xlsx --bolsa dados/A__o_Petrobras_tratado.xlsx --volatilidade dados/volatilidade_tratado.xlsx
```

Os nomes são apenas exemplos: conferir os arquivos reais na pasta `dados/`. O script original do grupo ainda não gera volatilidade. É necessário que Ryan forneça essa terceira série, com fonte e definição documentadas.

Testes: `python -m unittest discover -s tests -v`.

## Integração com backend
```python
from ia_svr.modelo import ModeloSVR
modelo = ModeloSVR().carregar('resultados/modelo_svr.joblib')
resposta = modelo.prever(dolar=5.25, bolsa=22.50, volatilidade=18.0)
```

A API recebe três números positivos, nas mesmas unidades e significado usados no treinamento, e devolve `fechamento_previsto`, `recomendacao`, `variacao_prevista_pct`, `aviso`.

## Limitações importantes
- Este é um protótipo de integração: durante o treino usa **valores reais observados na data t** para prever o fechamento em t+1, e não as previsões multistep. A avaliação não demonstra o desempenho do pipeline final do grupo.
- Quando os modelos de Ryan estiverem prontos, é preciso criar previsões históricas *out-of-sample* por janela expansiva para treinar e avaliar o SVR com as mesmas características que receberá na produção. Não misturar previsões futuras com informações reais futuras nem treinar/testar no mesmo intervalo.
- Confirmar a definição do horizonte (próximo pregão), a ação-alvo e o índice de volatilidade. Os dados de dólar e ação podem ter calendários diferentes; a junção usa apenas datas em comum.
- A recomendação é uma regra didática de limiar de 2%, não estratégia validada, nem aconselhamento financeiro.
- O script de coleta existente é do grupo e não é alterado por esta entrega.
