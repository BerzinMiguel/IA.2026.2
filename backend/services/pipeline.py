"""Atualização diária: dados -> IA -> histórico local.

Fluxo do escopo:
 1. Após o fechamento: dados de dólar, bolsa e volatilidade atualizados (cotacoes)
 2-4. Módulo de IA (multistep + SVR + decisão) gera previsões e recomendação
 5. Backend grava previsão, valores usados e recomendação para comparação futura
"""
import json

from .dados import carregar_historico, datas_disponiveis
from .ia import validar_saida


def executar(conn, funcao_ia, data_referencia: str | None = None, sobrescrever=False) -> dict:
    datas = datas_disponiveis(conn)
    if not datas:
        raise RuntimeError("sem dados de cotação; rode scripts/importar_dados.py antes")
    data_ref = data_referencia or datas[-1]

    existente = conn.execute(
        "SELECT id FROM execucoes WHERE data_referencia = ?", (data_ref,)
    ).fetchone()
    if existente and not sobrescrever:
        return {"data_referencia": data_ref, "status": "ja_existia", "execucao_id": existente["id"]}
    if existente:
        conn.execute("DELETE FROM execucoes WHERE id = ?", (existente["id"],))

    historico = carregar_historico(conn, ate=data_ref)  # sem vazamento de futuro
    saida = validar_saida(funcao_ia(historico, data_ref))

    cur = conn.execute(
        """INSERT INTO execucoes (data_referencia, versao_modelo, recomendacao, confianca,
                                  previsao_final, data_alvo_final, entradas_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            data_ref,
            saida["versao_modelo"],
            saida["recomendacao"],
            saida.get("confianca"),
            float(saida["previsao_final"]["valor"]),
            saida["previsao_final"]["data"],
            json.dumps(saida.get("entradas", {}), ensure_ascii=False),
        ),
    )
    exec_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO previsoes (execucao_id, indicador, data_alvo, valor_previsto) VALUES (?,?,?,?)",
        [
            (exec_id, ind, p["data"], float(p["valor"]))
            for ind, pts in saida["previsoes"].items()
            for p in pts
        ],
    )
    conn.commit()
    return {"data_referencia": data_ref, "status": "ok", "execucao_id": exec_id,
            "recomendacao": saida["recomendacao"]}


def backfill(conn, funcao_ia, dias: int = 60) -> list[dict]:
    """Roda a IA para os últimos `dias` pregões, cada um vendo só o seu passado.
    Gera o histórico de previsões x reais que alimenta as telas 2 e 3."""
    datas = datas_disponiveis(conn)[-dias:]
    return [executar(conn, funcao_ia, d) for d in datas]
