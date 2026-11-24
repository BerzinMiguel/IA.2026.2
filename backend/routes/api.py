"""Endpoints da API.

As seis primeiras rotas são exatamente as que `front/js/api.js` consome
(contrato combinado com o front). As demais expõem o mesmo histórico com mais
detalhe e são usadas pelos testes e por quem quiser inspecionar o banco.

Convenção de caso: as rotas do front devolvem a recomendação em MAIÚSCULAS
(APLICAR | MANTER | RETIRAR), como o `api.js` espera; o banco e as rotas
detalhadas usam minúsculas.
"""
import json

from flask import Blueprint, current_app, jsonify, request

from ia.decisao import avaliar_posicao

from ..db import INDICADORES, get_db
from ..services import cotacoes as servico_cotacoes
from ..services import metricas, pipeline
from ..services.ia import ContratoInvalido, obter_funcao_ia

bp = Blueprint("api", __name__, url_prefix="/api")

AVISO = "Protótipo acadêmico. Não constitui recomendação de investimento."


def _indicador_valido(ind):
    if ind not in INDICADORES:
        return jsonify(erro=f"indicador inválido; use um de {list(INDICADORES)}"), 400
    return None


def _nan_para_none(registros):
    return [{k: (None if v != v else v) for k, v in r.items()} for r in registros]


def _inteiro(nome, padrao, maximo):
    try:
        return max(1, min(int(request.args.get(nome, padrao)), maximo))
    except (TypeError, ValueError):
        return padrao


def _ultima_execucao(db):
    return db.execute(
        "SELECT * FROM execucoes ORDER BY data_referencia DESC LIMIT 1"
    ).fetchone()


def _entradas(execucao) -> dict:
    return json.loads(execucao["entradas_json"] or "{}")


def _variacao_pct(execucao, entradas, valor_referencia):
    """Variação prevista em %: a calculada pela IA, ou derivada do fechamento."""
    if entradas.get("variacao_prevista_pct") is not None:
        return entradas["variacao_prevista_pct"]
    if valor_referencia and execucao["previsao_final"] is not None:
        return round((execucao["previsao_final"] / valor_referencia - 1) * 100, 3)
    return None


def _bolsa_em(db, data):
    linha = db.execute(
        "SELECT valor FROM cotacoes WHERE data=? AND indicador='bolsa'", (data,)
    ).fetchone()
    return linha["valor"] if linha else None


# =====================================================================
# Contrato com o front (front/js/api.js)
# =====================================================================

@bp.get("/health")
def health():
    db = get_db()
    n = db.execute("SELECT COUNT(*) AS n FROM cotacoes").fetchone()["n"]
    ultima = db.execute("SELECT MAX(data_referencia) AS d FROM execucoes").fetchone()["d"]
    return jsonify(status="ok", ia_mode=current_app.config["IA_MODE"],
                   cotacoes=n, ultima_execucao=ultima)


@bp.get("/previsao/atual")
def previsao_atual():
    """Tela 1: recomendação do dia e os três indicadores previstos."""
    db = get_db()
    e = _ultima_execucao(db)
    if e is None:
        return jsonify(erro="nenhuma previsão gerada ainda; chame POST /api/atualizar"), 404

    atuais = {
        r["indicador"]: r["valor"]
        for r in db.execute("SELECT indicador, valor FROM cotacoes WHERE data=?",
                            (e["data_referencia"],))
    }
    # Previsto de cada indicador na mesma data-alvo da decisão (saída dos multistep).
    previstos = {
        r["indicador"]: r["valor_previsto"]
        for r in db.execute(
            "SELECT indicador, valor_previsto FROM previsoes WHERE execucao_id=? AND data_alvo=?",
            (e["id"], e["data_alvo_final"]))
    }
    if not previstos:  # horizonte da decisão sem ponto multistep: usa o último passo
        for r in db.execute(
            "SELECT indicador, data_alvo, valor_previsto FROM previsoes WHERE execucao_id=? "
            "ORDER BY data_alvo", (e["id"],)
        ):
            previstos[r["indicador"]] = r["valor_previsto"]

    entradas = _entradas(e)
    return jsonify({
        "data_atualizacao": e["data_referencia"],
        "data_alvo": e["data_alvo_final"],
        "indicadores": {
            ind: {"atual": atuais.get(ind), "previsto": previstos.get(ind)}
            for ind in INDICADORES
        },
        "fechamento_previsto": e["previsao_final"],
        "recomendacao": e["recomendacao"].upper(),
        "variacao_prevista_pct": _variacao_pct(e, entradas, atuais.get("bolsa")),
        "confianca": e["confianca"],
        "versao_modelo": e["versao_modelo"],
        "gerado_em": e["criado_em"],
        "aviso": AVISO,
    })


@bp.post("/decisao")
def decisao():
    """Tela 1: cruza a posição informada pelo usuário com a última previsão.

    Corpo (todos opcionais; sem posição informada, trata como quem não tem):

        {"quantidade": 100, "cotacao_entrada": 38.50}
        {"valor_investido": 3850.0, "cotacao_entrada": 38.50}

    Nada é gravado: a previsão é do mercado e é a mesma para todos; só o
    enquadramento muda por usuário.
    """
    db = get_db()
    e = _ultima_execucao(db)
    if e is None:
        return jsonify(erro="nenhuma previsão gerada ainda; chame POST /api/atualizar"), 404
    if e["previsao_final"] is None:
        return jsonify(erro="a última execução não tem fechamento previsto"), 404

    corpo = request.get_json(silent=True) or {}
    if not isinstance(corpo, dict):
        return jsonify(erro="corpo deve ser um objeto JSON"), 400

    entradas = _entradas(e)
    preco_atual = entradas.get("bolsa_atual") or _bolsa_em(db, e["data_referencia"])
    if not preco_atual:
        return jsonify(erro="sem fechamento da bolsa na data de referência"), 404

    # O limiar e o MAE saem da própria execução: a banda de indiferença tem de
    # acompanhar o erro do modelo que gerou aquela previsão.
    modelo = entradas.get("metricas_modelo") or {}
    try:
        resultado = avaliar_posicao(
            preco_atual=preco_atual,
            preco_previsto=e["previsao_final"],
            limiar_pct=entradas.get("limiar_pct", 2.0),
            quantidade=corpo.get("quantidade"),
            cotacao_entrada=corpo.get("cotacao_entrada"),
            valor_investido=corpo.get("valor_investido"),
            erro_modelo=modelo.get("MAE"),
            data_alvo=e["data_alvo_final"],
        )
    except ValueError as erro:
        return jsonify(erro=str(erro)), 400

    resultado["versao_modelo"] = e["versao_modelo"]
    resultado["data_atualizacao"] = e["data_referencia"]
    resultado["aviso"] = AVISO
    return jsonify(resultado)


@bp.get("/historico")
def historico():
    """Tela 2: série observada do indicador: [{data, valor}] em ordem crescente.

    `dias` conta pregões disponíveis no banco (não dias de calendário), para o
    gráfico não ficar vazio em feriados e fins de semana.
    """
    ind = request.args.get("indicador", "bolsa")
    if (err := _indicador_valido(ind)):
        return err
    dias = _inteiro("dias", 30, 5000)
    linhas = get_db().execute(
        "SELECT data, valor FROM cotacoes WHERE indicador=? ORDER BY data DESC LIMIT ?",
        (ind, dias)
    ).fetchall()
    return jsonify([{"data": r["data"], "valor": r["valor"]} for r in reversed(linhas)])


@bp.get("/recomendacoes")
def recomendacoes():
    """Tela 2: recomendações passadas, da mais recente para a mais antiga."""
    db = get_db()
    dias = _inteiro("dias", 30, 1000)
    linhas = db.execute(
        """SELECT e.data_referencia, e.data_alvo_final, e.previsao_final, e.recomendacao,
                  e.confianca, e.versao_modelo, e.entradas_json, c.valor AS referencia
           FROM execucoes e
           LEFT JOIN cotacoes c ON c.data = e.data_referencia AND c.indicador = 'bolsa'
           ORDER BY e.data_referencia DESC LIMIT ?""", (dias,)
    ).fetchall()
    return jsonify([{
        "data": r["data_referencia"],
        "data_alvo": r["data_alvo_final"],
        "fechamento_previsto": r["previsao_final"],
        "variacao_prevista_pct": _variacao_pct(r, _entradas(r), r["referencia"]),
        "recomendacao": r["recomendacao"].upper(),
        "confianca": r["confianca"],
        "versao_modelo": r["versao_modelo"],
    } for r in linhas])


@bp.get("/avaliacao")
def avaliacao():
    """Telas 2 e 3: previsões já com fechamento real conhecido.

    Equivale ao `resultados/avaliacao_svr.csv` da IA, porém calculado sobre o
    histórico que o backend gravou dia a dia (walk-forward), não sobre o corte
    de teste do treino.
    """
    ind = request.args.get("indicador", "bolsa")
    if (err := _indicador_valido(ind)):
        return err
    df = metricas.previsoes_vs_reais(get_db(), ind).dropna(subset=["real"])
    df = df.assign(erro=(df.real - df.previsto).round(6)).sort_values("data_alvo")
    colunas = ["data_referencia", "data_alvo", "real", "previsto", "erro", "recomendacao"]
    return jsonify(_nan_para_none(df[colunas].to_dict(orient="records")))


@bp.get("/metricas")
def metricas_modelo():
    """Tela 3: erro do modelo no histórico gravado + amostras do treino do SVR."""
    db = get_db()
    ind = request.args.get("indicador", "bolsa")
    if (err := _indicador_valido(ind)):
        return err
    resumo = metricas.resumo(metricas.previsoes_vs_reais(db, ind))

    e = _ultima_execucao(db)
    modelo = _entradas(e).get("metricas_modelo", {}) if e else {}
    return jsonify({
        "indicador": ind,
        "MAE": resumo["mae"],
        "RMSE": resumo["rmse"],
        "MAPE_pct": resumo["mape"],
        "acerto_direcao": resumo["acerto_direcao"],
        "n_avaliadas": resumo["n_avaliadas"],
        "amostras_treino": modelo.get("amostras_treino"),
        "amostras_teste": modelo.get("amostras_teste"),
        "versao_modelo": e["versao_modelo"] if e else None,
        "modelo": modelo,
        "observacao": (
            "MAE, RMSE e MAPE vêm das previsões gravadas dia a dia e comparadas ao "
            "fechamento real; amostras_treino/teste vêm do treino do SVR. "
            "Resultado acadêmico: erro medido não é rentabilidade."
        ),
    })


@bp.post("/atualizar")
def atualizar():
    """Rodada diária: dados -> IA -> histórico. Chamada pelo botão e pelo cron.

    Com `baixar: true` busca antes os pregões novos nas fontes (PTAX do Banco
    Central e fechamento da ação no Yahoo) e regrava as planilhas de `dados/`.
    Sem isso, apenas reprocessa o que já está no banco — e para uma data que já
    tem execução devolve `ja_existia` sem recalcular nada.
    """
    cfg = current_app.config
    corpo = request.get_json(silent=True) or {}
    sincronizacao = None
    if corpo.get("baixar"):
        try:
            sincronizacao = servico_cotacoes.sincronizar(get_db())
        except servico_cotacoes.FalhaAoSincronizar as e:
            return jsonify(erro=str(e)), 502
        except (ValueError, OSError) as e:
            return jsonify(erro=f"falha ao sincronizar cotações: {e}"), 502
    try:
        fn = obter_funcao_ia(cfg["IA_MODE"], cfg["IA_MODULE"], cfg["HORIZONTE"])
        res = pipeline.executar(get_db(), fn, corpo.get("data_referencia"),
                                sobrescrever=bool(corpo.get("sobrescrever")))
    except ContratoInvalido as e:
        return jsonify(erro=f"saída da IA fora do contrato: {e}"), 502
    except RuntimeError as e:
        return jsonify(erro=str(e)), 409
    except (ValueError, ImportError, OSError) as e:
        return jsonify(erro=f"falha ao executar a IA: {e}"), 502
    resposta = {**res, "data_atualizacao": res["data_referencia"]}
    if sincronizacao is not None:
        resposta["sincronizacao"] = sincronizacao
    return jsonify(resposta)


# =====================================================================
# Rotas detalhadas (diagnóstico, testes e uso futuro do front)
# =====================================================================

@bp.get("/visao-geral")
def visao_geral():
    """Como /previsao/atual, mas com todos os passos previstos e as entradas da decisão."""
    db = get_db()
    e = _ultima_execucao(db)
    if e is None:
        return jsonify(erro="nenhuma previsão gerada ainda; chame POST /api/atualizar"), 404

    previsoes = {ind: [] for ind in INDICADORES}
    for p in db.execute(
        "SELECT indicador, data_alvo, valor_previsto FROM previsoes WHERE execucao_id=? "
        "ORDER BY data_alvo", (e["id"],)
    ):
        previsoes[p["indicador"]].append({"data": p["data_alvo"], "valor": p["valor_previsto"]})

    atuais = {
        r["indicador"]: r["valor"]
        for r in db.execute("SELECT indicador, valor FROM cotacoes WHERE data=?",
                            (e["data_referencia"],))
    }
    return jsonify(
        data_referencia=e["data_referencia"],
        gerado_em=e["criado_em"],
        versao_modelo=e["versao_modelo"],
        recomendacao=e["recomendacao"],
        confianca=e["confianca"],
        previsao_final={"indicador": "bolsa", "data": e["data_alvo_final"],
                        "valor": e["previsao_final"]},
        valores_atuais=atuais,
        previsoes=previsoes,
        entradas=_entradas(e),
        aviso=AVISO,
    )


@bp.get("/desempenho")
def desempenho():
    """Métricas dos três indicadores, acerto das recomendações e série de erro."""
    db = get_db()
    por_indicador = {}
    serie_erro = []
    acerto = {"n_avaliadas": 0, "taxa_acerto": None}
    for ind in INDICADORES:
        df = metricas.previsoes_vs_reais(db, ind)
        por_indicador[ind] = metricas.resumo(df)
        if ind == "bolsa":
            av = df.dropna(subset=["real"])
            serie_erro = [{"data": r.data_alvo, "erro": round(r.real - r.previsto, 6)}
                          for r in av.itertuples()]
            acerto = metricas.acerto_recomendacoes(df)
    return jsonify(metricas=por_indicador, recomendacoes=acerto, serie_erro_bolsa=serie_erro,
                   observacao="bolsa = previsão final do SVR; dólar e volatilidade = "
                              "último passo dos modelos multistep")


@bp.get("/indicadores/<ind>")
def indicador(ind):
    """Série observada por intervalo de datas."""
    if (err := _indicador_valido(ind)):
        return err
    inicio = request.args.get("inicio", "0000-01-01")
    fim = request.args.get("fim", "9999-12-31")
    linhas = get_db().execute(
        "SELECT data, valor FROM cotacoes WHERE indicador=? AND data BETWEEN ? AND ? "
        "ORDER BY data", (ind, inicio, fim)
    ).fetchall()
    return jsonify(indicador=ind, pontos=[dict(r) for r in linhas])
