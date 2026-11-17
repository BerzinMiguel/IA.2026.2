# Multistep

## Instalação

```bash
python -m pip install --upgrade pip
python -m pip install numpy pandas openpyxl
```

## Importação e uso

```python
from ia.multistep import Multistep

modelo = Multistep()
previsoes = modelo.Modelo_multistep(
    "treino.xlsx", "validacao.xlsx", "teste.xlsx",
    coluna_treino=1, coluna_validacao=1, coluna_teste=1,
    dimensao=12, horizonte=2,
)
```

## Funções

- `normalizar_bases`: calcula mínimo e máximo somente no treino e aplica essa escala ao treino, validação e teste.
- `prever_horizonte`: ajusta por mínimos quadrados um modelo direto para um horizonte, usando lags da série.
- `Modelo_multistep`: executa as duas etapas e retorna previsões `[t+1, ..., t+horizonte]` na escala original.

Cada horizonte é ajustado separadamente com `β = pinv(X) @ y`. Validação e teste são usados como histórico recente para prever após o último dado disponível; não participam do ajuste dos coeficientes. Os arquivos precisam ter a mesma coluna-alvo; seu índice começa em zero.

## Integração temporal com SVR

`prever_serie(treino, historico, dimensao, horizonte)` oferece a mesma regressão
em memória, com validações de finitude e tamanho. Veja README_LAYS.md para
o pipeline dos três indicadores e treino fora da amostra. Os métodos originais
continuam disponíveis e preservam seu comportamento com arquivos.
