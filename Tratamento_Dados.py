"""Coleta e tratamento de séries temporais financeiras.

Dependências: pandas, requests e openpyxl (instale com
``python -m pip install pandas requests openpyxl``).

O módulo guarda um arquivo bruto e um arquivo tratado para cada ativo. A
planilha tratada contém somente Data, Hora e Valor, em ordem cronológica.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd
import requests


class ImportadorDados(ABC):
    """Classe base para provedores que baixam uma série e geram planilha."""

    def __init__(self, ativo: str, pasta: str | Path = "dados") -> None:
        self.ativo = ativo
        self.pasta = Path(pasta)
        # O nome do arquivo usa um identificador simples e seguro.
        seguro = "".join(c if c.isalnum() or c in "-_" else "_" for c in ativo)
        self.arquivo_bruto = self.pasta / f"{seguro}_bruto.xlsx"

    @abstractmethod
    def buscar_dados(self, inicio: date, fim: date) -> pd.DataFrame:
        """Busca no provedor e retorna Data, Hora, Valor e Ativo."""

    def importar_dados(self, inicio: date, fim: date) -> Path:
        """Baixa a série, ordena por data/hora e salva a planilha bruta."""
        if inicio > fim:
            raise ValueError("A data inicial deve ser anterior ou igual à data final.")
        dados = self.buscar_dados(inicio, fim)
        dados = _normalizar_colunas(dados)
        self.pasta.mkdir(parents=True, exist_ok=True)
        dados.to_excel(self.arquivo_bruto, index=False)
        return self.arquivo_bruto


class ImportadorBancoCentral(ImportadorDados):
    """Importa a cotação diária de venda do dólar (série SGS 10813/PTAX)."""

    URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"

    def __init__(self, serie: int = 10813, ativo: str = "Dólar", **kwargs) -> None:
        super().__init__(ativo, **kwargs)
        self.serie = serie

    def buscar_dados(self, inicio: date, fim: date) -> pd.DataFrame:
        # A API do SGS recebe datas no formato dd/mm/aaaa.
        params = {
            "formato": "json",
            "dataInicial": inicio.strftime("%d/%m/%Y"),
            "dataFinal": fim.strftime("%d/%m/%Y"),
        }
        resposta = requests.get(self.URL.format(serie=self.serie), params=params, timeout=30)
        resposta.raise_for_status()
        registros = resposta.json()
        linhas = [
            {"Data": pd.to_datetime(item["data"], dayfirst=True), "Hora": "", "Valor": item["valor"], "Ativo": self.ativo}
            for item in registros
        ]
        return pd.DataFrame(linhas, columns=["Data", "Hora", "Valor", "Ativo"])


class ImportadorAcaoB3(ImportadorDados):
    """Importa fechamentos diários de uma ação B3 via endpoint de gráficos Yahoo.

    Informe o ticker Yahoo, por exemplo ``PETR4.SA`` ou ``VALE3.SA``.
    A API retorna candles diários; apenas o campo de fechamento é usado.
    """

    URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

    def __init__(self, ticker: str = "PETR4.SA", ativo: Optional[str] = None, **kwargs) -> None:
        self.ticker = ticker
        super().__init__(ativo or ticker, **kwargs)

    def buscar_dados(self, inicio: date, fim: date) -> pd.DataFrame:
        # O limite superior da API é exclusivo; somamos um dia para incluir fim.
        inicio_utc = int(datetime.combine(inicio, time.min, ZoneInfo("UTC")).timestamp())
        fim_utc = int(datetime.combine(fim + timedelta(days=1), time.min, ZoneInfo("UTC")).timestamp())
        params = {"period1": inicio_utc, "period2": fim_utc, "interval": "1d", "events": "history"}
        headers = {"User-Agent": "Mozilla/5.0 (compatible; DataCollector/1.0)"}
        resposta = requests.get(self.URL.format(ticker=quote(self.ticker)), params=params, headers=headers, timeout=30)
        resposta.raise_for_status()
        payload = resposta.json().get("chart", {})
        if payload.get("error"):
            raise RuntimeError(f"Erro do provedor Yahoo Finance: {payload['error']}")
        resultado = (payload.get("result") or [None])[0]
        if resultado is None:
            return pd.DataFrame(columns=["Data", "Hora", "Valor", "Ativo"])
        timestamps = resultado.get("timestamp") or []
        cotacoes = resultado.get("indicators", {}).get("quote", [{}])[0]
        fechamentos = cotacoes.get("close") or []
        linhas = []
        for instante, fechamento in zip(timestamps, fechamentos):
            if fechamento is None:
                continue
            # Preserva a data de negociação local da B3; a hora fica vazia
            # porque cada candle representa o fechamento diário, não intradiário.
            dia = datetime.fromtimestamp(instante, ZoneInfo("America/Sao_Paulo")).date()
            linhas.append({"Data": pd.Timestamp(dia), "Hora": "", "Valor": fechamento, "Ativo": self.ativo})
        return pd.DataFrame(linhas, columns=["Data", "Hora", "Valor", "Ativo"])


def _normalizar_colunas(dados: pd.DataFrame) -> pd.DataFrame:
    """Aplica schema comum e ordenação estável sem deslocar valores entre datas."""
    colunas = ["Data", "Hora", "Valor", "Ativo"]
    if dados.empty:
        return pd.DataFrame(columns=colunas)
    dados = dados.copy()
    for coluna in colunas:
        if coluna not in dados:
            dados[coluna] = "" if coluna == "Hora" else pd.NA
    dados["Data"] = pd.to_datetime(dados["Data"], errors="coerce")
    dados["Valor"] = pd.to_numeric(dados["Valor"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    dados = dados.dropna(subset=["Data", "Valor"])
    return dados[colunas].sort_values(["Data", "Hora"], kind="stable", na_position="last").reset_index(drop=True)


class TratadorDados:
    """Lê uma planilha bruta, remove registros inválidos e grava a tratada."""

    def __init__(self, pasta_saida: str | Path = "dados") -> None:
        self.pasta_saida = Path(pasta_saida)

    def tratar_dados(
        self,
        planilha: str | Path,
        hora_fechamento: Optional[str] = None,
        coluna_valor: str = "Valor",
        nome_ativo: Optional[str] = None,
    ) -> Path:
        """Mantém datas/valores válidos e, opcionalmente, apenas a hora definida.

        Para séries diárias, ``Hora`` pode vir vazia: cada linha já representa
        um fechamento diário. Para dados intradiários, informe, por exemplo,
        ``hora_fechamento="17:00"``; só linhas exatamente nesse horário ficam.
        Fins de semana e feriados sem cotação não são preenchidos artificialmente.
        """
        origem = Path(planilha)
        dados = pd.read_excel(origem)
        if "Data" not in dados or coluna_valor not in dados:
            raise ValueError("A planilha precisa conter as colunas 'Data' e 'Valor'.")
        if "Hora" not in dados:
            dados["Hora"] = ""
        dados["Data"] = pd.to_datetime(dados["Data"], errors="coerce")
        dados[coluna_valor] = pd.to_numeric(
            dados[coluna_valor].astype(str).str.replace(",", ".", regex=False), errors="coerce"
        )
        # Remove linhas sem data, sem preço ou com células vazias nos campos usados.
        dados = dados.dropna(subset=["Data", coluna_valor]).copy()
        dados["Hora"] = dados["Hora"].fillna("").astype(str).str.strip()
        dados = dados[dados["Hora"].str.lower().ne("nan")]
        if hora_fechamento is not None:
            # Compara HH:MM para tolerar horas vindas do Excel como HH:MM:SS.
            hora_alvo = hora_fechamento[:5]
            dados = dados[dados["Hora"].str.slice(0, 5).eq(hora_alvo)]
        if nome_ativo is None:
            nome_ativo = str(dados["Ativo"].dropna().iloc[0]) if "Ativo" in dados and not dados["Ativo"].dropna().empty else origem.stem.replace("_bruto", "")
        # A ordenação é feita pelo par da mesma linha; nenhum preço é separado da data.
        tratados = dados.assign(Valor=dados[coluna_valor], Ativo=nome_ativo)
        tratados = tratados[["Data", "Hora", "Valor", "Ativo"]]
        tratados = tratados.sort_values(["Data", "Hora"], kind="stable").drop_duplicates(
            subset=["Data", "Hora"], keep="last"
        ).reset_index(drop=True)
        self.pasta_saida.mkdir(parents=True, exist_ok=True)
        destino = self.pasta_saida / f"{origem.stem.replace('_bruto', '')}_tratado.xlsx"
        tratados.to_excel(destino, index=False)
        return destino


if __name__ == "__main__":
    # Exemplo: baixe dólar e PETR4 em arquivos separados e trate cada um.
    data_inicial = date(2020, 1, 1)
    data_final = date.today()
    importadores = [ImportadorBancoCentral(), ImportadorAcaoB3("PETR4.SA", ativo="Ação Petrobras")]
    tratador = TratadorDados()
    for importador in importadores:
        arquivo = importador.importar_dados(data_inicial, data_final)
        arquivo_tratado = tratador.tratar_dados(arquivo)
        print(f"{importador.ativo}: {arquivo} -> {arquivo_tratado}")
