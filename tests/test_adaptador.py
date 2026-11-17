"""Testes da ponte IA -> backend (ia/adaptador.py), com o modelo real.

Usa séries curtas e hiperparâmetros pequenos para o treino caber em segundos.
"""
import numpy as np
import pandas as pd
import pytest

from backend import create_app
from backend.db import connect
from backend.services import pipeline
from backend.services.dados import salvar_serie, volatilidade_diaria
from backend.services.ia import obter_funcao_ia, validar_saida
from ia import adaptador

INDICADORES = ("dolar", "bolsa", "volatilidade")


@pytest.fixture(autouse=True)
def modelo_pequeno(monkeypatch):
    monkeypatch.setenv("IA_DIMENSAO", "3")
    monkeypatch.setenv("IA_HORIZONTE", "2")
    monkeypatch.setenv("IA_MINIMO_TREINO", "20")
    monkeypatch.delenv("IA_ARTEFATO", raising=False)
    adaptador.limpar_cache()
    yield
    adaptador.limpar_cache()


def series(n=90):
    datas = pd.bdate_range("2025-01-01", periods=n)
    t = np.arange(n)
    bolsa = pd.Series(30 + t * 0.02 + np.cos(t / 7) * 0.3, index=datas)
    dolar = pd.Series(5 + t * 0.001 + np.sin(t / 4) * 0.02, index=datas)
    return {"dolar": dolar, "bolsa": bolsa, "volatilidade": volatilidade_diaria(bolsa)}


def data(historico, posicao):
    return historico["bolsa"].index[posicao].strftime("%Y-%m-%d")


def test_saida_respeita_o_contrato_do_backend():
    historico = series()
    referencia = data(historico, -1)
    saida = validar_saida(adaptador.gerar_recomendacao(historico, referencia))

    assert saida["recomendacao"] in ("aplicar", "manter", "retirar")
    assert saida["versao_modelo"].startswith("multistep+svr")
    for indicador in INDICADORES:
        pontos = saida["previsoes"][indicador]
        assert len(pontos) == 2
        assert all(ponto["data"] > referencia for ponto in pontos)
        assert [p["data"] for p in pontos] == sorted(p["data"] for p in pontos)
    # Decisão no último horizonte: a previsão final cai na mesma data-alvo.
    assert saida["previsao_final"]["data"] == saida["previsoes"]["bolsa"][-1]["data"]
    assert 0 <= saida["confianca"] <= 1
    assert saida["entradas"]["metricas_modelo"]["amostras_treino"] > 0
    assert saida["entradas"]["horizonte_decisao"] == 2


def test_nao_usa_dados_posteriores_a_data_referencia():
    historico = series()
    corte = data(historico, 70)
    esperado = adaptador.gerar_recomendacao(historico, corte)

    adaptador.limpar_cache()
    adulterado = {nome: serie.copy() for nome, serie in historico.items()}
    for serie in adulterado.values():
        serie[serie.index > pd.Timestamp(corte)] *= 3  # futuro irreconhecível
    obtido = adaptador.gerar_recomendacao(adulterado, corte)

    assert obtido == esperado


def test_cache_reaproveita_treino_antigo_e_retreina_ao_voltar_no_tempo():
    historico = series()
    primeiro = adaptador.gerar_recomendacao(historico, data(historico, 70))
    treinado = adaptador._CACHE["pipeline"]

    # Data posterior: modelo treinado no passado continua válido (sem vazamento).
    posterior = adaptador.gerar_recomendacao(historico, data(historico, 80))
    assert adaptador._CACHE["pipeline"] is treinado
    assert posterior["previsao_final"]["data"] > primeiro["previsao_final"]["data"]

    # Data anterior ao treino em cache: precisa treinar de novo.
    adaptador.gerar_recomendacao(historico, data(historico, 60))
    assert adaptador._CACHE["pipeline"] is not treinado


def test_horizonte_de_decisao_configuravel(monkeypatch):
    historico = series()
    referencia = data(historico, -1)
    monkeypatch.setenv("IA_HORIZONTE_DECISAO", "1")
    saida = adaptador.gerar_recomendacao(historico, referencia)
    assert saida["previsao_final"]["data"] == saida["previsoes"]["bolsa"][0]["data"]
    assert saida["entradas"]["horizonte_decisao"] == 1

    monkeypatch.setenv("IA_HORIZONTE_DECISAO", "9")
    with pytest.raises(ValueError):
        adaptador.gerar_recomendacao(historico, referencia)


def test_historico_insuficiente_e_recusado():
    with pytest.raises(ValueError):
        adaptador.gerar_recomendacao(series(15), data(series(15), -1))


def test_backend_ponta_a_ponta_com_ia_real(tmp_path):
    """Dados -> multistep -> SVR -> gravação -> rotas do front."""
    app = create_app({"DB_PATH": str(tmp_path / "real.db"), "TESTING": True,
                      "IA_MODE": "real", "IA_MODULE": "ia.adaptador:gerar_recomendacao"})
    conn = connect(app.config["DB_PATH"])
    for nome, serie in series().items():
        salvar_serie(conn, nome, serie)
    funcao = obter_funcao_ia("real", "ia.adaptador:gerar_recomendacao", 5)
    execucoes = pipeline.backfill(conn, funcao, 5)
    conn.close()
    assert len(execucoes) == 5 and all(e["status"] == "ok" for e in execucoes)

    cliente = app.test_client()
    atual = cliente.get("/api/previsao/atual").get_json()
    assert atual["recomendacao"] in ("APLICAR", "MANTER", "RETIRAR")
    assert atual["versao_modelo"].startswith("multistep+svr")
    assert atual["indicadores"]["bolsa"]["previsto"] is not None

    metricas = cliente.get("/api/metricas").get_json()
    assert metricas["amostras_treino"] > 0 and metricas["amostras_teste"] > 0
    assert metricas["n_avaliadas"] > 0

    avaliacao = cliente.get("/api/avaliacao").get_json()
    assert avaliacao and all(item["real"] is not None for item in avaliacao)
