"""Ponte entre o backend e o módulo de inteligência.

CONTRATO
--------
O módulo de IA expõe UMA função:

    gerar_recomendacao(historico: dict[str, pd.Series], data_referencia: str) -> dict

- `historico` tem as chaves "dolar", "bolsa", "volatilidade"; cada Series é
  indexada por data e contém SOMENTE dados até `data_referencia` (inclusive).
- Retorno esperado:

    {
      "versao_modelo": "multistep+svr-d12-h2-t2025-07-17",
      "previsoes": {                          # saídas dos 3 multistep
        "dolar":        [{"data": "2026-11-17", "valor": 5.31}, ...],
        "bolsa":        [{"data": "2026-11-17", "valor": 37.9}, ...],
        "volatilidade": [{"data": "2026-11-17", "valor": 1.42}, ...]
      },
      "previsao_final": {"data": "2026-11-18", "valor": 38.4},   # SVR (bolsa)
      "recomendacao": "aplicar" | "manter" | "retirar",
      "confianca": 0.0 a 1.0 (ou null),
      "entradas": { ...valores usados na decisão, livre... }
    }

Implementações:
- `ia.adaptador:gerar_recomendacao`  → Multistep + SVR (modo "real", padrão)
- `ia_simulada` abaixo               → mesmo contrato, sem modelo (modo "mock")
- `ia/exemplo.py`                    → esqueleto mínimo, para consulta

Toda data-alvo é obrigatória: o backend grava previsão por data e compara com o
fechamento real daquele dia. Saída sem data é recusada com HTTP 502.
"""
import importlib

import numpy as np
import pandas as pd

RECOMENDACOES = ("aplicar", "manter", "retirar")

# Mesma banda de indiferença do modelo real (ia/svr/modelo.py: 2%).
LIMIAR_PADRAO = 0.02


class ContratoInvalido(ValueError):
    pass


def validar_saida(saida: dict) -> dict:
    if not isinstance(saida, dict):
        raise ContratoInvalido("a IA deve retornar um dict")
    for chave in ("versao_modelo", "previsoes", "previsao_final", "recomendacao"):
        if chave not in saida:
            raise ContratoInvalido(f"campo obrigatório ausente: {chave}")
    if saida["recomendacao"] not in RECOMENDACOES:
        raise ContratoInvalido(f"recomendacao inválida: {saida['recomendacao']}")
    for ind in ("dolar", "bolsa", "volatilidade"):
        pts = saida["previsoes"].get(ind)
        if not pts:
            raise ContratoInvalido(f"previsoes.{ind} vazio ou ausente")
        for p in pts:
            if not p.get("data") or "valor" not in p:
                raise ContratoInvalido(f"previsoes.{ind}: cada ponto precisa de data e valor")
            float(p["valor"])
    pf = saida["previsao_final"]
    if not pf.get("data") or "valor" not in pf:
        raise ContratoInvalido("previsao_final precisa de data e valor")
    c = saida.get("confianca")
    if c is not None and not (0 <= float(c) <= 1):
        raise ContratoInvalido("confianca deve estar entre 0 e 1")
    return saida


def ia_simulada(historico: dict, data_referencia: str, horizonte: int = 5) -> dict:
    """Substituto do modelo real: tendência recente + a mesma regra de decisão.

    Não é o modelo do projeto; existe para o front e o backend rodarem sem
    scikit-learn e sem esperar o treino. Segue exatamente o mesmo contrato e o
    mesmo limiar de 2% usado pelo SVR, para as telas se comportarem igual.
    """
    datas_futuras = pd.bdate_range(pd.Timestamp(data_referencia) + pd.Timedelta(days=1),
                                   periods=horizonte)
    previsoes = {}
    for ind in ("dolar", "bolsa", "volatilidade"):
        s = historico[ind].dropna()
        ultimo = float(s.iloc[-1])
        if ind == "volatilidade":
            # Volatilidade diária (|ln(Pt/Pt-1)|*100) tende à média recente.
            media = float(s.tail(60).mean())
            vals = [ultimo + (media - ultimo) * (1 - 0.9 ** (h + 1)) for h in range(horizonte)]
        else:
            drift = float(np.log(s.tail(21)).diff().mean())
            vals = [ultimo * np.exp(drift * (h + 1)) for h in range(horizonte)]
        previsoes[ind] = [
            {"data": d.strftime("%Y-%m-%d"), "valor": round(float(v), 6)}
            for d, v in zip(datas_futuras, vals)
        ]

    bolsa_atual = float(historico["bolsa"].iloc[-1])
    final = previsoes["bolsa"][-1]
    variacao = final["valor"] / bolsa_atual - 1

    if variacao > LIMIAR_PADRAO:
        rec = "aplicar"
    elif variacao < -LIMIAR_PADRAO:
        rec = "retirar"
    else:
        rec = "manter"

    return {
        "versao_modelo": "mock-v1",
        "previsoes": previsoes,
        "previsao_final": dict(final),
        "recomendacao": rec,
        "confianca": round(min(1.0, abs(variacao) / (2 * LIMIAR_PADRAO)), 3),
        "entradas": {
            "bolsa_atual": round(bolsa_atual, 6),
            "dolar_atual": round(float(historico["dolar"].iloc[-1]), 6),
            "volatilidade_atual": round(float(historico["volatilidade"].iloc[-1]), 6),
            "variacao_prevista_pct": round(variacao * 100, 3),
            "limiar_pct": LIMIAR_PADRAO * 100,
            "horizonte_decisao": horizonte,
            "aviso": "IA simulada: resultado sem valor preditivo.",
        },
    }


def obter_funcao_ia(modo: str, modulo: str, horizonte: int):
    if modo == "mock":
        return lambda hist, data_ref: ia_simulada(hist, data_ref, horizonte)
    if modo == "real":
        nome_mod, _, nome_fn = modulo.partition(":")
        fn = getattr(importlib.import_module(nome_mod), nome_fn)
        return fn
    raise ValueError(f"IA_MODE desconhecido: {modo}")
