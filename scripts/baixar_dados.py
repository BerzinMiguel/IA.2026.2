"""Baixa e trata as séries reais, gerando as planilhas de dados/.

Usa os importadores de `ia/tratamento.py`: dólar pela API de séries do Banco
Central (PTAX de venda) e a ação pelo endpoint de cotações diárias do Yahoo.
Gera também a planilha de volatilidade a partir dos fechamentos da ação.

    python scripts/baixar_dados.py
    python scripts/baixar_dados.py --inicio 2018-01-01 --ticker VALE3.SA

As planilhas tratadas ficam versionadas no repositório, então só é preciso
rodar isto para atualizar a base com pregões novos. Depois:

    python scripts/importar_dados.py --reais
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from backend.config import Config  # noqa: E402
from ia.tratamento import (ImportadorAcaoB3, ImportadorBancoCentral,  # noqa: E402
                           TratadorDados, gerar_planilha_volatilidade_diaria)


def resumir(caminho: Path) -> str:
    df = pd.read_excel(caminho)
    return (f"{len(df)} linhas, de {df.Data.min().date()} a {df.Data.max().date()}, "
            f"último valor {df.Valor.iloc[-1]:.4f}")


def main():
    p = argparse.ArgumentParser(description="Baixa e trata as séries do projeto")
    p.add_argument("--inicio", default="2020-01-01", help="data inicial YYYY-MM-DD")
    p.add_argument("--fim", default=date.today().isoformat(), help="data final YYYY-MM-DD")
    p.add_argument("--ticker", default="PETR4.SA", help="ticker da ação no Yahoo")
    p.add_argument("--pasta", default=Config.DATA_DIR)
    a = p.parse_args()

    inicio, fim = date.fromisoformat(a.inicio), date.fromisoformat(a.fim)
    pasta = Path(a.pasta)
    tratador = TratadorDados(pasta)

    importadores = [
        ImportadorBancoCentral(ativo="Dolar", pasta=pasta),
        ImportadorAcaoB3(a.ticker, ativo="Petrobras", pasta=pasta),
    ]
    tratadas = {}
    for importador in importadores:
        print(f"baixando {importador.ativo}...", flush=True)
        tratada = tratador.tratar_dados(importador.importar_dados(inicio, fim))
        print(f"  {resumir(tratada)}")
        tratadas[importador.ativo] = tratada

    volatilidade = gerar_planilha_volatilidade_diaria(tratadas["Petrobras"],
                                                      pasta / "volatilidade.xlsx")
    print(f"volatilidade gerada em {volatilidade.name}")
    print("\nPróximo passo: python scripts/importar_dados.py --reais")


if __name__ == "__main__":
    main()
