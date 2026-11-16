# Tratamento de dados financeiros

## Instalação

Atualize o instalador e instale as bibliotecas usadas pelo arquivo:

```bash
python -m pip install --upgrade pip
python -m pip install pandas requests openpyxl
```

## Funções

- `ImportadorBancoCentral`: baixa a série diária do dólar pelo SGS do Banco Central.
- `ImportadorAcaoB3`: baixa os fechamentos diários de um ticker B3 via Yahoo Finance (por exemplo, `PETR4.SA`).
- `ImportadorDados.importar_dados`: salva a coleta bruta em Excel.
- `TratadorDados.tratar_dados`: valida e ordena os registros e salva a planilha tratada.
- `gerar_planilha_volatilidade_diaria`: recebe uma planilha com `Data` e `Valor` e cria outra com `Data`, `Volatilidade_Diaria` e `Ativo`.

As planilhas ficam em ordem cronológica crescente, com a data mais recente na última linha. A volatilidade é o módulo do retorno logarítmico percentual entre dois fechamentos consecutivos e é atribuída à data do fechamento mais recente. A primeira data não tem valor de volatilidade, pois não existe fechamento anterior. Fins de semana e feriados não são preenchidos artificialmente.

Exemplo:

```python
from Tratamento_Dados import gerar_planilha_volatilidade_diaria

arquivo = gerar_planilha_volatilidade_diaria("dados/PETR4_tratado.xlsx")
print(arquivo)
```
