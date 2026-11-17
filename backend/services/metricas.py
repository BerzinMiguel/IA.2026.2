"""Avaliação da IA: compara previsões gravadas com os fechamentos reais."""
import numpy as np
import pandas as pd


def previsoes_vs_reais(conn, indicador: str = "bolsa") -> pd.DataFrame:
    """Previsão final do SVR (bolsa) ou o último passo de um multistep, vs real."""
    if indicador == "bolsa":
        sql = """
            SELECT e.data_referencia, e.data_alvo_final AS data_alvo,
                   e.previsao_final AS previsto, c.valor AS real,
                   ref.valor AS valor_referencia, e.recomendacao
            FROM execucoes e
            JOIN cotacoes ref ON ref.data = e.data_referencia AND ref.indicador = 'bolsa'
            LEFT JOIN cotacoes c ON c.data = e.data_alvo_final AND c.indicador = 'bolsa'
            ORDER BY e.data_referencia
        """
        return pd.read_sql_query(sql, conn)
    sql = """
        SELECT e.data_referencia, p.data_alvo, p.valor_previsto AS previsto,
               c.valor AS real, ref.valor AS valor_referencia, e.recomendacao
        FROM execucoes e
        JOIN previsoes p ON p.execucao_id = e.id AND p.indicador = :ind
        JOIN cotacoes ref ON ref.data = e.data_referencia AND ref.indicador = :ind
        LEFT JOIN cotacoes c ON c.data = p.data_alvo AND c.indicador = :ind
        WHERE p.data_alvo = (SELECT MAX(data_alvo) FROM previsoes
                             WHERE execucao_id = e.id AND indicador = :ind)
        ORDER BY e.data_referencia
    """
    return pd.read_sql_query(sql, conn, params={"ind": indicador})


def resumo(df: pd.DataFrame) -> dict:
    av = df.dropna(subset=["real"])
    if av.empty:
        return {"n_avaliadas": 0, "mae": None, "rmse": None, "mape": None,
                "acerto_direcao": None}
    erro = av.previsto - av.real
    dir_prev = np.sign(av.previsto - av.valor_referencia)
    dir_real = np.sign(av.real - av.valor_referencia)
    return {
        "n_avaliadas": int(len(av)),
        "mae": round(float(erro.abs().mean()), 6),
        "rmse": round(float(np.sqrt((erro ** 2).mean())), 6),
        "mape": round(float((erro.abs() / av.real.abs()).mean() * 100), 4),
        "acerto_direcao": round(float((dir_prev == dir_real).mean()), 4),
    }


def acerto_recomendacoes(df: pd.DataFrame) -> dict:
    """aplicar acerta se o preço subiu; retirar acerta se caiu; manter não é avaliado."""
    av = df.dropna(subset=["real"])
    av = av[av.recomendacao != "manter"]
    if av.empty:
        return {"n_avaliadas": 0, "taxa_acerto": None}
    subiu = av.real > av.valor_referencia
    ok = ((av.recomendacao == "aplicar") & subiu) | ((av.recomendacao == "retirar") & ~subiu)
    return {"n_avaliadas": int(len(av)), "taxa_acerto": round(float(ok.mean()), 4)}
