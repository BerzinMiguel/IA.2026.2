"""Carrega as séries no banco local.

Com as planilhas reais que vêm no repositório (dados/):
    python scripts/importar_dados.py --reais

Com planilhas suas:
    python scripts/importar_dados.py --dolar dados/dolar.csv --bolsa dados/acao.csv \
        [--volatilidade dados/volatilidade.xlsx]

Sem planilhas (série sintética, só para demonstração):
    python scripts/importar_dados.py --exemplo
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import Config  # noqa: E402
from backend.db import connect, init_db  # noqa: E402
from backend.services.dados import gerar_dados_exemplo, importar_planilhas  # noqa: E402

# Nomes gerados por scripts/baixar_dados.py e versionados no repositório.
PADRAO = {
    "dolar": "Dolar_tratado.xlsx",
    "bolsa": "Petrobras_tratado.xlsx",
    "volatilidade": "volatilidade.xlsx",
}

p = argparse.ArgumentParser()
p.add_argument("--reais", action="store_true",
               help="usa as planilhas versionadas em dados/ (dólar PTAX e PETR4)")
p.add_argument("--dolar")
p.add_argument("--bolsa")
p.add_argument("--volatilidade", help="opcional; se omitido, calcula a partir da bolsa")
p.add_argument("--exemplo", action="store_true")
a = p.parse_args()

conn = connect(Config.DB_PATH)
init_db(conn)

if a.reais:
    pasta = Path(Config.DATA_DIR)
    caminhos = {chave: pasta / nome for chave, nome in PADRAO.items()}
    ausentes = [c.name for c in caminhos.values() if not c.is_file()]
    if ausentes:
        p.error(f"não encontrei {ausentes} em {pasta}; rode scripts/baixar_dados.py")
    print("Importado:", importar_planilhas(conn, caminhos["dolar"], caminhos["bolsa"],
                                           caminhos["volatilidade"]))
elif a.exemplo:
    print("Dados de exemplo:", gerar_dados_exemplo(conn))
elif a.dolar and a.bolsa:
    print("Importado:", importar_planilhas(conn, a.dolar, a.bolsa, a.volatilidade))
else:
    p.error("informe --reais, --exemplo, ou --dolar e --bolsa")
