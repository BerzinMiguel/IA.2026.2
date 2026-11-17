"""Carga e leitura das séries históricas (dólar, bolsa, volatilidade).

Definição de volatilidade
-------------------------
É a mesma do tratamento de dados (`ia/tratamento.py`, função
`gerar_planilha_volatilidade_diaria`): o módulo do retorno logarítmico diário
em pontos percentuais, `|ln(P_t / P_{t-1})| * 100`, associado à data `t`.
O SVR foi treinado com essa série. Usar outra definição aqui (por exemplo,
desvio-padrão anualizado) mudaria a entrada do modelo e invalidaria as
métricas, então ela precisa ser a mesma nos dois lugares.
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

COLUNAS_DATA = ("date", "data", "datetime", "dia")
COLUNAS_VALOR = ("close", "fechamento", "adj close", "adj_close", "valor", "price",
                 "preco", "preço", "volatilidade_diaria", "volatilidade")


def _ler_planilha(caminho: Path) -> pd.Series:
    """Lê CSV/XLSX e devolve uma Series indexada por data com o valor diário."""
    if caminho.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(caminho)
    else:
        df = pd.read_csv(caminho, sep=None, engine="python")
    df.columns = [str(c).strip() for c in df.columns]
    lower = {c.lower(): c for c in df.columns}

    col_data = next((lower[c] for c in COLUNAS_DATA if c in lower), None)
    col_valor = next((lower[c] for c in COLUNAS_VALOR if c in lower), None)
    if col_data is None or col_valor is None:
        raise ValueError(
            f"{caminho.name}: não achei colunas de data/valor. Colunas: {list(df.columns)}"
        )

    brutas = df[col_data].astype(str).str.strip()
    # ISO (2025-01-13) não pode usar dayfirst; formato BR (13/01/2025) precisa dele
    iso = brutas.str.match(r"^\d{4}-\d{2}-\d{2}").all()
    datas = pd.to_datetime(brutas.str[:10] if iso else brutas,
                           format="%Y-%m-%d" if iso else None,
                           dayfirst=not iso, errors="coerce")
    valores = pd.to_numeric(
        df[col_valor].astype(str).str.replace(",", ".", regex=False), errors="coerce"
    )
    s = pd.Series(valores.values, index=datas).dropna()
    s = s[~s.index.isna()].sort_index()
    return s[~s.index.duplicated(keep="last")]


def volatilidade_diaria(bolsa: pd.Series) -> pd.Series:
    """|ln(P_t / P_{t-1})| * 100, na data t, igual ao tratamento de dados."""
    bolsa = bolsa[bolsa > 0].sort_index()
    return (np.log(bolsa / bolsa.shift(1)).abs() * 100).dropna()


def salvar_serie(conn: sqlite3.Connection, indicador: str, serie: pd.Series):
    linhas = [(d.strftime("%Y-%m-%d"), indicador, float(v)) for d, v in serie.items()]
    conn.executemany(
        "INSERT OR REPLACE INTO cotacoes (data, indicador, valor) VALUES (?, ?, ?)", linhas
    )
    conn.commit()
    return len(linhas)


def importar_planilhas(conn, dolar: Path, bolsa: Path, volatilidade: Path | None = None) -> dict:
    """Importa as planilhas tratadas. Sem a de volatilidade, calcula a partir da bolsa."""
    s_dolar = _ler_planilha(Path(dolar))
    s_bolsa = _ler_planilha(Path(bolsa))
    s_vol = _ler_planilha(Path(volatilidade)) if volatilidade else volatilidade_diaria(s_bolsa)
    return {
        "dolar": salvar_serie(conn, "dolar", s_dolar),
        "bolsa": salvar_serie(conn, "bolsa", s_bolsa),
        "volatilidade": salvar_serie(conn, "volatilidade", s_vol),
    }


def gerar_dados_exemplo(conn, inicio="2020-01-02", fim="2026-11-13", seed=42) -> dict:
    """Séries sintéticas plausíveis, só para demonstrar enquanto não há dados reais."""
    rng = np.random.default_rng(seed)
    datas = pd.bdate_range(inicio, fim)
    n = len(datas)
    dolar = 5.2 * np.exp(np.cumsum(rng.normal(0.00005, 0.008, n)))
    bolsa = 18.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.022, n)))
    s_bolsa = pd.Series(bolsa, index=datas)
    return {
        "dolar": salvar_serie(conn, "dolar", pd.Series(dolar, index=datas)),
        "bolsa": salvar_serie(conn, "bolsa", s_bolsa),
        "volatilidade": salvar_serie(conn, "volatilidade", volatilidade_diaria(s_bolsa)),
    }


def carregar_historico(conn, ate: str | None = None) -> dict[str, pd.Series]:
    """Séries até `ate` (inclusive). Garante que a IA nunca vê dados futuros."""
    sql = "SELECT data, indicador, valor FROM cotacoes"
    params: tuple = ()
    if ate:
        sql += " WHERE data <= ?"
        params = (ate,)
    df = pd.read_sql_query(sql + " ORDER BY data", conn, params=params, parse_dates=["data"])
    out = {}
    for ind in ("dolar", "bolsa", "volatilidade"):
        sub = df[df.indicador == ind]
        out[ind] = pd.Series(sub.valor.values, index=sub.data.values, name=ind)
    return out


def datas_disponiveis(conn) -> list[str]:
    linhas = conn.execute(
        "SELECT data FROM cotacoes WHERE indicador='bolsa' ORDER BY data"
    ).fetchall()
    return [r["data"] for r in linhas]
