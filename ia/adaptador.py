"""Ponte entre a IA (Multistep + SVR) e o backend.

O backend chama uma função, sempre com o mesmo contrato:

    gerar_recomendacao(historico: dict[str, pd.Series], data_referencia: str) -> dict

`historico` traz as chaves "dolar", "bolsa" e "volatilidade", cada uma com os
valores somente até `data_referencia` (garantia do backend). Aqui esses dados
são alinhados pela interseção de datas (`carregar_bases`), passam pelos três
multistep e pelo SVR por horizonte, e voltam no formato que
`backend/services/ia.py` valida e grava.

Variáveis de ambiente, todas opcionais:

    IA_DIMENSAO           lags usados pelo multistep (12)
    IA_HORIZONTE          passos previstos (2)
    IA_MINIMO_TREINO      observações mínimas antes da primeira origem (60)
    IA_LIMIAR             banda de indiferença da decisão (0.02)
    IA_MAX_OBS_TREINO     usa só as N últimas observações (0 = a série toda)
    IA_ARTEFATO           pipeline.joblib já treinado, dispensa treinar
    IA_HORIZONTE_DECISAO  horizonte usado na decisão (0 = o último)

Treino e cache
--------------
Treinar percorre todas as origens da série e custa dezenas de segundos, então o
pipeline treinado fica em cache no processo. O cache só é reaproveitado quando
foi treinado com dados anteriores ou iguais à `data_referencia` pedida, o que
mantém o backfill walk-forward sem vazamento: o modelo do dia 10 nunca viu o
dia 11. Pedir uma data mais antiga que o treino em cache força um novo treino.
Em produção o processo diário é novo a cada execução, portanto treina com os
dados do dia. Para congelar um modelo, treine com `scripts/treinar_svr.py` e
aponte `IA_ARTEFATO` para o `pipeline.joblib` gerado.
"""
from __future__ import annotations

import os
import threading

import pandas as pd

from ia.svr.integracao import PipelineIntegrado, carregar_bases

INDICADORES = ("dolar", "bolsa", "volatilidade")

_CACHE: dict = {"chave": None, "pipeline": None, "treinado_ate": None}
_TRAVA = threading.Lock()


def _opcoes() -> dict:
    """Lê a configuração a cada chamada (facilita testes e troca sem reiniciar)."""
    return {
        "dimensao": int(os.getenv("IA_DIMENSAO", "12")),
        "horizonte": int(os.getenv("IA_HORIZONTE", "2")),
        "minimo_treino": int(os.getenv("IA_MINIMO_TREINO", "60")),
        "limiar": float(os.getenv("IA_LIMIAR", "0.02")),
        "max_obs": int(os.getenv("IA_MAX_OBS_TREINO", "0")),
        "artefato": os.getenv("IA_ARTEFATO") or None,
        "horizonte_decisao": int(os.getenv("IA_HORIZONTE_DECISAO", "0")),
    }


def limpar_cache() -> None:
    """Descarta o pipeline em memória (usado nos testes e ao trocar de modelo)."""
    with _TRAVA:
        _CACHE.update(chave=None, pipeline=None, treinado_ate=None)


def _quadros(historico: dict[str, pd.Series]) -> list[pd.DataFrame]:
    """Series do backend -> DataFrames no formato esperado por `carregar_bases`."""
    quadros = []
    for indicador in INDICADORES:
        serie = historico.get(indicador)
        if serie is None or serie.dropna().empty:
            raise ValueError(f"histórico sem dados de {indicador}")
        serie = serie.dropna().sort_index()
        serie = serie[~serie.index.duplicated(keep="last")]
        coluna = "Volatilidade_Diaria" if indicador == "volatilidade" else "Valor"
        quadros.append(pd.DataFrame({
            "Data": pd.to_datetime(serie.index),
            coluna: serie.to_numpy(dtype=float),
        }))
    return quadros


def _treinar(quadros: list[pd.DataFrame], opcoes: dict) -> PipelineIntegrado:
    if opcoes["max_obs"]:
        quadros = [quadro.tail(opcoes["max_obs"]) for quadro in quadros]
    pipeline = PipelineIntegrado(
        dimensao=opcoes["dimensao"],
        horizonte=opcoes["horizonte"],
        minimo_treino=opcoes["minimo_treino"],
        limiar=opcoes["limiar"],
    )
    pipeline.treinar(*quadros)  # sem pasta_saida: nada é gravado em disco aqui
    return pipeline


def _carregar_artefato(caminho: str, data_referencia: pd.Timestamp) -> PipelineIntegrado:
    pipeline = PipelineIntegrado.carregar(caminho)
    if pipeline.limite_treino > data_referencia:
        raise ValueError(
            f"{caminho} foi treinado com dados até {pipeline.limite_treino.date()}, "
            f"posteriores a {data_referencia.date()}; isso vazaria o futuro na avaliação"
        )
    return pipeline


def _obter_pipeline(quadros, data_referencia: pd.Timestamp, opcoes: dict) -> PipelineIntegrado:
    """Devolve um pipeline treinado somente com dados até `data_referencia`."""
    chave = (opcoes["dimensao"], opcoes["horizonte"], opcoes["minimo_treino"],
             opcoes["limiar"], opcoes["max_obs"], opcoes["artefato"])
    if (_CACHE["chave"] == chave and _CACHE["pipeline"] is not None
            and _CACHE["treinado_ate"] <= data_referencia):
        return _CACHE["pipeline"]

    if opcoes["artefato"]:
        pipeline = _carregar_artefato(opcoes["artefato"], data_referencia)
        treinado_ate = pipeline.limite_treino
    else:
        pipeline = _treinar(quadros, opcoes)
        treinado_ate = data_referencia

    _CACHE.update(chave=chave, pipeline=pipeline, treinado_ate=treinado_ate)
    return pipeline


def _datas_alvo(origem: pd.Timestamp, horizonte: int) -> pd.DatetimeIndex:
    """Próximos `horizonte` dias úteis após a última observação.

    Não considera feriados da B3: se a data-alvo cair em feriado, o backend
    simplesmente não encontra fechamento real e aquela previsão fica sem
    comparação (`real` nulo), em vez de ser comparada com o dia errado.
    """
    return pd.bdate_range(origem + pd.Timedelta(days=1), periods=horizonte)


def gerar_recomendacao(historico: dict[str, pd.Series], data_referencia: str) -> dict:
    opcoes = _opcoes()
    limite = pd.Timestamp(data_referencia).normalize()

    quadros = _quadros(historico)
    # Corta de novo pela data de referência: o backend já entrega o histórico
    # truncado, mas o treino não deve depender disso.
    quadros = [quadro[quadro.Data <= limite] for quadro in quadros]
    dados, avisos = carregar_bases(*quadros)
    if dados.empty:
        raise ValueError(f"sem datas comuns às três séries até {data_referencia}")

    with _TRAVA:
        pipeline = _obter_pipeline(quadros, limite, opcoes)
        horizonte = pipeline.horizonte
        decisao = opcoes["horizonte_decisao"] or horizonte
        if not 1 <= decisao <= horizonte:
            raise ValueError(f"IA_HORIZONTE_DECISAO deve estar entre 1 e {horizonte}")
        # A janela de previsão é sempre a atual; os modelos continuam os do treino.
        pipeline.dados, pipeline.avisos = dados, avisos
        resposta = pipeline.prever(_datas_alvo(dados.Data.iloc[-1], horizonte))

    pontos = resposta["previsoes"]
    escolhido = pontos[decisao - 1]
    variacao = escolhido["variacao_prevista_pct"]
    limiar_pct = pipeline.limiar * 100
    metricas = pipeline.metricas[str(decisao)]
    atuais = {nome: float(dados.iloc[-1][nome]) for nome in INDICADORES}

    return {
        "versao_modelo": (f"multistep+svr-d{pipeline.dimensao}-h{horizonte}"
                          f"-t{metricas['ultimo_alvo_treino']}"),
        "previsoes": {
            indicador: [
                {"data": ponto["data_alvo"],
                 "valor": round(float(ponto["indicadores"][indicador]["previsto"]), 6)}
                for ponto in pontos
            ]
            for indicador in INDICADORES
        },
        "previsao_final": {"data": escolhido["data_alvo"],
                           "valor": round(float(escolhido["fechamento_previsto"]), 6)},
        "recomendacao": escolhido["recomendacao"].lower(),
        # Distância relativa ao limiar, não probabilidade: 1.0 = variação prevista
        # de duas vezes o limiar ou mais.
        "confianca": (round(min(1.0, abs(variacao) / (2 * limiar_pct)), 3)
                      if limiar_pct > 0 else None),
        "entradas": {
            "bolsa_atual": round(atuais["bolsa"], 6),
            "dolar_atual": round(atuais["dolar"], 6),
            "volatilidade_atual": round(atuais["volatilidade"], 6),
            "variacao_prevista_pct": variacao,
            "limiar_pct": round(limiar_pct, 4),
            "horizonte_decisao": decisao,
            "observacoes_alinhadas": int(len(dados)),
            "metricas_modelo": metricas,
            "avisos": resposta["avisos"],
            "aviso": escolhido["aviso"],
        },
    }
