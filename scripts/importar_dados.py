"""Carrega as séries no banco local.

Com as planilhas do tratamento de dados:
    python scripts/importar_dados.py --dolar data/dolar.csv --bolsa data/petrobras.csv [--volatilidade data/vol.csv]

Sem planilhas (dados sintéticos para demonstração):
    python scripts/importar_dados.py --exemplo
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import Config  # noqa: E402
from backend.db import connect, init_db  # noqa: E402
from backend.services.dados import gerar_dados_exemplo, importar_planilhas  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--dolar")
p.add_argument("--bolsa")
p.add_argument("--volatilidade", help="opcional; se omitido, calcula a partir da bolsa")
p.add_argument("--exemplo", action="store_true")
a = p.parse_args()

conn = connect(Config.DB_PATH)
init_db(conn)
if a.exemplo:
    print("Dados de exemplo:", gerar_dados_exemplo(conn))
elif a.dolar and a.bolsa:
    print("Importado:", importar_planilhas(conn, a.dolar, a.bolsa, a.volatilidade))
else:
    p.error("informe --dolar e --bolsa, ou --exemplo")
