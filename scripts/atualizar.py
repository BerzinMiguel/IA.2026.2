"""Atualização diária (rodar após o fechamento da bolsa, ex.: cron às 18h30).

    python scripts/atualizar.py                 # roda para o último pregão
    python scripts/atualizar.py --backfill 60   # gera histórico dos últimos 60 pregões
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import Config  # noqa: E402
from backend.db import connect, init_db  # noqa: E402
from backend.services import pipeline  # noqa: E402
from backend.services.ia import obter_funcao_ia  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--data", help="data de referência YYYY-MM-DD")
p.add_argument("--backfill", type=int, help="quantidade de pregões passados")
a = p.parse_args()

conn = connect(Config.DB_PATH)
init_db(conn)
fn = obter_funcao_ia(Config.IA_MODE, Config.IA_MODULE, Config.HORIZONTE)

if a.backfill:
    res = pipeline.backfill(conn, fn, a.backfill)
    print(f"{len(res)} execuções; última: {res[-1]}")
else:
    print(pipeline.executar(conn, fn, a.data))
