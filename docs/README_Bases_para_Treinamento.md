# Bases para treinamento

## Instalação

```bash
python -m pip install --upgrade pip
python -m pip install pandas openpyxl
```

## Importação

```python
from ia.bases import PreparadorBases

preparador = PreparadorBases()
```

## Funções

- `dividir_base`: separa a planilha em X, Y e Z, pela ordem das datas e sem embaralhar linhas. Padrão: 70%, 15%, 15%.
- `ajustar_min_max`: calcula mínimo e máximo na base fornecida (use a base de treino) e retorna os parâmetros da escala, além de salvar a base transformada.
- `aplicar_min_max`: aplica os parâmetros já calculados a outra base, sem recalcular mínimo ou máximo.

A transformação é `x_norm = (x - mínimo_treino) / (máximo_treino - mínimo_treino)`. O índice da coluna começa em zero. Entradas CSV, texto tabular, Excel, JSON, Parquet, Feather e HTML são aceitas; alguns formatos exigem dependências adicionais do pandas. As saídas são salvas em Excel.
