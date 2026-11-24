"""Busca cotações novas nas fontes e carrega no banco.

É o mesmo caminho de `scripts/baixar_dados.py` + `scripts/importar_dados.py`,
exposto para o botão Atualizar do front poder puxar pregões novos em vez de
só reprocessar o que já está no banco.

Fontes: PTAX de venda pela API de séries do Banco Central, e o fechamento
diário da ação pelo endpoint de cotações do Yahoo. A volatilidade é derivada
dos fechamentos da ação, não baixada.

Atenção: isto **reescreve as planilhas de `dados/`**, que são versionadas no
repositório. É o comportamento do script original (é assim que a base do
projeto é atualizada), mas significa que sincronizar deixa o repositório sujo.
Nenhum valor histórico muda; a atualização apenas acrescenta os pregões novos.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ia.tratamento import (ImportadorAcaoB3, ImportadorBancoCentral,
                           TratadorDados, gerar_planilha_volatilidade_diaria)

from ..config import Config
from .dados import datas_disponiveis, importar_planilhas

TICKER_PADRAO = "PETR4.SA"
INICIO_PADRAO = "2020-01-01"


class FalhaAoSincronizar(RuntimeError):
    """As fontes externas não responderam ou devolveram série inutilizável."""


def sincronizar(conn, *, inicio: str = INICIO_PADRAO, fim: str | None = None,
                ticker: str = TICKER_PADRAO, pasta: str | Path | None = None) -> dict:
    """Baixa, trata e importa as três séries. Devolve o que mudou.

    A contagem de pregões novos é feita contra o banco antes da importação,
    para o front poder dizer se havia mesmo algo a buscar.
    """
    pasta = Path(pasta or Config.DATA_DIR)
    inicio_d = date.fromisoformat(inicio)
    fim_d = date.fromisoformat(fim) if fim else date.today()
    if inicio_d > fim_d:
        raise ValueError("A data inicial não pode ser posterior à final.")

    antes = datas_disponiveis(conn)
    ultima_antes = antes[-1] if antes else None

    tratador = TratadorDados(pasta)
    planilhas = {}
    for importador in (ImportadorBancoCentral(ativo="Dolar", pasta=pasta),
                       ImportadorAcaoB3(ticker, ativo="Petrobras", pasta=pasta)):
        try:
            bruta = importador.importar_dados(inicio_d, fim_d)
            planilhas[importador.ativo] = tratador.tratar_dados(bruta)
        except Exception as erro:  # rede, formato inesperado, série vazia
            raise FalhaAoSincronizar(
                f"não foi possível baixar {importador.ativo}: {erro}"
            ) from erro

    volatilidade = gerar_planilha_volatilidade_diaria(
        planilhas["Petrobras"], pasta / "volatilidade.xlsx"
    )
    importar_planilhas(conn, planilhas["Dolar"], planilhas["Petrobras"], volatilidade)
    conn.commit()

    depois = datas_disponiveis(conn)
    novas = [d for d in depois if ultima_antes is None or d > ultima_antes]
    return {
        "ultima_data_antes": ultima_antes,
        "ultima_data": depois[-1] if depois else None,
        "pregoes_novos": len(novas),
        "datas_novas": novas[-10:],
        "ticker": ticker,
    }
