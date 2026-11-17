"""Esqueleto mínimo do contrato backend <-> IA, para consulta.

A implementação de verdade é `ia/adaptador.py` (multistep + SVR). Este arquivo
fica como referência: é o menor retorno válido possível, útil para testar o
backend com outro modelo sem mexer em nada do resto.

    IA_MODE=real IA_MODULE=ia.exemplo:gerar_recomendacao python run.py

Regras do contrato (validadas em backend/services/ia.py):
- o backend garante que `historico` não contém datas posteriores a
  `data_referencia`; não burle isso lendo arquivos por fora;
- toda data-alvo é obrigatória, porque o backend grava previsão por data e
  compara com o fechamento real daquele dia;
- `recomendacao` só pode ser "aplicar", "manter" ou "retirar".
"""
import pandas as pd


def gerar_recomendacao(historico: dict[str, pd.Series], data_referencia: str) -> dict:
    dolar = historico["dolar"]          # Series: índice = data, valor = fechamento
    bolsa = historico["bolsa"]          # ação acompanhada (ex.: PETR4)
    vol = historico["volatilidade"]     # |ln(Pt/Pt-1)| * 100

    # No modelo real, aqui entram: os três multistep (ia/multistep.py) e o SVR
    # que consolida as previsões e estima o fechamento futuro (ia/svr/).
    datas = pd.bdate_range(pd.Timestamp(data_referencia) + pd.Timedelta(days=1), periods=5)
    ultimo = lambda s: float(s.iloc[-1])  # noqa: E731  (placeholder: repete o último valor)

    return {
        "versao_modelo": "exemplo-v1",
        "previsoes": {
            "dolar": [{"data": d.strftime("%Y-%m-%d"), "valor": ultimo(dolar)} for d in datas],
            "bolsa": [{"data": d.strftime("%Y-%m-%d"), "valor": ultimo(bolsa)} for d in datas],
            "volatilidade": [{"data": d.strftime("%Y-%m-%d"), "valor": ultimo(vol)} for d in datas],
        },
        "previsao_final": {"data": datas[-1].strftime("%Y-%m-%d"), "valor": ultimo(bolsa)},
        "recomendacao": "manter",
        "confianca": None,
        "entradas": {"observacao": "placeholder sem modelo"},
    }
