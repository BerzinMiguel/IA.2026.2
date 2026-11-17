"""Testes do backend: contrato com o front, histórico e proteção contra vazamento.

Rodam com a IA simulada (rápida); a IA real é exercitada em test_adaptador.py.
"""
import numpy as np
import pandas as pd
import pytest

from backend import create_app
from backend.db import connect, init_db
from backend.services import pipeline
from backend.services.dados import (carregar_historico, gerar_dados_exemplo,
                                    importar_planilhas, volatilidade_diaria)
from backend.services.ia import ContratoInvalido, ia_simulada, validar_saida

INDICADORES = ("dolar", "bolsa", "volatilidade")


@pytest.fixture
def app(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "t.db"), "TESTING": True})
    conn = connect(app.config["DB_PATH"])
    gerar_dados_exemplo(conn, inicio="2025-01-01", fim="2026-11-13")
    fn = lambda h, d: ia_simulada(h, d, 5)  # noqa: E731
    pipeline.backfill(conn, fn, 30)
    conn.close()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------- contrato consumido por front/js/api.js ----------

def test_health(client):
    r = client.get("/api/health").get_json()
    assert r["status"] == "ok" and r["cotacoes"] > 0


def test_previsao_atual(client):
    r = client.get("/api/previsao/atual").get_json()
    assert r["recomendacao"] in ("APLICAR", "MANTER", "RETIRAR")
    assert r["data_atualizacao"] == "2026-11-13"
    assert r["data_alvo"] > r["data_atualizacao"]
    assert set(r["indicadores"]) == set(INDICADORES)
    for ind in INDICADORES:
        assert r["indicadores"][ind]["atual"] is not None
        assert r["indicadores"][ind]["previsto"] is not None
    assert r["fechamento_previsto"] is not None
    assert r["variacao_prevista_pct"] is not None
    assert 0 <= r["confianca"] <= 1


def test_historico_serie(client):
    r = client.get("/api/historico?indicador=bolsa&dias=5").get_json()
    assert isinstance(r, list) and len(r) == 5
    assert [p["data"] for p in r] == sorted(p["data"] for p in r)
    assert all(isinstance(p["valor"], float) for p in r)
    assert client.get("/api/historico?indicador=bitcoin").status_code == 400


def test_recomendacoes(client):
    r = client.get("/api/recomendacoes?dias=10").get_json()
    assert isinstance(r, list) and len(r) == 10
    assert [i["data"] for i in r] == sorted((i["data"] for i in r), reverse=True)
    assert all(i["recomendacao"] in ("APLICAR", "MANTER", "RETIRAR") for i in r)
    assert all(i["variacao_prevista_pct"] is not None for i in r)


def test_avaliacao(client):
    r = client.get("/api/avaliacao").get_json()
    assert isinstance(r, list) and r
    assert all(i["real"] is not None and i["previsto"] is not None for i in r)
    primeiro = r[0]
    assert primeiro["erro"] == pytest.approx(primeiro["real"] - primeiro["previsto"], abs=1e-6)
    assert primeiro["data_alvo"] > primeiro["data_referencia"]


def test_metricas(client):
    r = client.get("/api/metricas").get_json()
    assert r["n_avaliadas"] > 0
    assert r["MAE"] >= 0 and r["RMSE"] >= r["MAE"] and r["MAPE_pct"] >= 0
    assert 0 <= r["acerto_direcao"] <= 1
    # IA simulada não treina: amostras ficam nulas e o front mostra "--"
    assert r["amostras_treino"] is None and r["amostras_teste"] is None
    assert r["observacao"]


def test_atualizar_idempotente(client):
    r = client.post("/api/atualizar").get_json()
    assert r["status"] == "ja_existia"
    assert r["data_atualizacao"] == "2026-11-13"


def test_front_servido(client):
    assert b"IA Bolsa" in client.get("/").data
    assert client.get("/js/api.js").status_code == 200
    assert client.get("/api/nao-existe").status_code == 404
    assert client.get("/nao-existe.js").status_code == 404


# ---------- rotas detalhadas ----------

def test_visao_geral(client):
    r = client.get("/api/visao-geral").get_json()
    assert r["recomendacao"] in ("aplicar", "manter", "retirar")
    assert set(r["previsoes"]) == set(INDICADORES)
    assert len(r["previsoes"]["bolsa"]) == 5
    assert r["data_referencia"] == "2026-11-13"


def test_desempenho(client):
    d = client.get("/api/desempenho").get_json()
    assert d["metricas"]["bolsa"]["n_avaliadas"] > 0
    assert d["metricas"]["bolsa"]["mae"] is not None
    assert len(d["serie_erro_bolsa"]) > 0


def test_indicador_e_validacao(client):
    r = client.get("/api/indicadores/dolar?inicio=2026-11-01").get_json()
    assert all(p["data"] >= "2026-11-01" for p in r["pontos"])
    assert client.get("/api/indicadores/bitcoin").status_code == 400


# ---------- dados e contrato ----------

def test_sem_vazamento_de_futuro(app):
    conn = connect(app.config["DB_PATH"])
    hist = carregar_historico(conn, ate="2026-06-01")
    for s in hist.values():
        assert s.index.max() <= pd.Timestamp("2026-06-01")


def test_contrato_rejeita_saida_ruim():
    with pytest.raises(ContratoInvalido):
        validar_saida({"versao_modelo": "x", "previsoes": {}, "previsao_final": {},
                       "recomendacao": "comprar"})
    # data_alvo nula: PipelineIntegrado devolve null sem calendário futuro
    sem_data = {
        "versao_modelo": "x",
        "previsoes": {i: [{"data": None, "valor": 1.0}] for i in INDICADORES},
        "previsao_final": {"data": None, "valor": 1.0},
        "recomendacao": "manter",
    }
    with pytest.raises(ContratoInvalido):
        validar_saida(sem_data)


def test_volatilidade_igual_ao_tratamento_de_dados():
    """Mesma definição de ia/tratamento.py: |ln(Pt/Pt-1)| * 100."""
    precos = pd.Series([10.0, 10.5, 10.2], index=pd.bdate_range("2025-01-01", periods=3))
    vol = volatilidade_diaria(precos)
    assert len(vol) == 2
    assert vol.iloc[0] == pytest.approx(abs(np.log(10.5 / 10.0)) * 100)


def test_importa_csv_formato_br(tmp_path):
    (tmp_path / "d.csv").write_text("Data;Fechamento\n02/01/2025;6,10\n03/01/2025;6,05\n")
    datas = pd.bdate_range("2025-01-01", periods=40)
    pd.DataFrame({"Date": datas, "Close": range(10, 50)}).to_csv(tmp_path / "b.csv", index=False)
    conn = connect(str(tmp_path / "x.db"))
    init_db(conn)
    n = importar_planilhas(conn, tmp_path / "d.csv", tmp_path / "b.csv")
    assert n["dolar"] == 2 and n["bolsa"] == 40 and n["volatilidade"] == 39


def test_importa_planilha_de_volatilidade_do_ryan(tmp_path):
    """A planilha de volatilidade usa a coluna Volatilidade_Diaria."""
    datas = pd.bdate_range("2025-01-01", periods=5)
    pd.DataFrame({"Data": datas, "Valor": [5.0, 5.1, 5.2, 5.1, 5.0]}).to_excel(
        tmp_path / "dolar.xlsx", index=False)
    pd.DataFrame({"Data": datas, "Valor": [30.0, 31.0, 30.5, 31.5, 32.0]}).to_excel(
        tmp_path / "bolsa.xlsx", index=False)
    pd.DataFrame({"Data": datas, "Volatilidade_Diaria": [None, 3.3, 1.6, 3.2, 1.6],
                  "Ativo": "Ação"}).to_excel(tmp_path / "vol.xlsx", index=False)
    conn = connect(str(tmp_path / "y.db"))
    init_db(conn)
    n = importar_planilhas(conn, tmp_path / "dolar.xlsx", tmp_path / "bolsa.xlsx",
                           tmp_path / "vol.xlsx")
    assert n == {"dolar": 5, "bolsa": 5, "volatilidade": 4}
