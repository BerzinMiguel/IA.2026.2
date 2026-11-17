import sqlite3
from pathlib import Path

from flask import current_app, g

INDICADORES = ("dolar", "bolsa", "volatilidade")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cotacoes (
    data        TEXT NOT NULL,          -- YYYY-MM-DD
    indicador   TEXT NOT NULL,          -- dolar | bolsa | volatilidade
    valor       REAL NOT NULL,
    PRIMARY KEY (data, indicador)
);

CREATE TABLE IF NOT EXISTS execucoes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    data_referencia  TEXT NOT NULL UNIQUE,  -- último fechamento usado pela IA
    criado_em        TEXT NOT NULL DEFAULT (datetime('now')),
    versao_modelo    TEXT NOT NULL,
    recomendacao     TEXT NOT NULL CHECK (recomendacao IN ('aplicar','manter','retirar')),
    confianca        REAL,
    previsao_final   REAL,                  -- fechamento futuro da bolsa (SVR)
    data_alvo_final  TEXT,
    entradas_json    TEXT                   -- valores usados na decisão
);

CREATE TABLE IF NOT EXISTS previsoes (
    execucao_id     INTEGER NOT NULL REFERENCES execucoes(id) ON DELETE CASCADE,
    indicador       TEXT NOT NULL,
    data_alvo       TEXT NOT NULL,
    valor_previsto  REAL NOT NULL,
    PRIMARY KEY (execucao_id, indicador, data_alvo)
);
"""


def connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)
    conn.commit()
