"""Divisão temporal e normalização Min–Max de bases tabulares.

Dependências: pandas e openpyxl. As divisões preservam a ordem das datas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


class PreparadorBases:
    """Divide uma base em ordem temporal e aplica normalização Min–Max.

    Para a coluna numérica escolhida, a escala é ajustada na base de treino:

        x_norm = (x - x_min) / (x_max - x_min)

    Os valores ``x_min`` e ``x_max`` retornados podem ser reutilizados em
    validação, teste ou novas bases, sem recalcular a escala com esses dados.
    """

    def __init__(self, pasta_saida: str | Path = "bases_treinamento") -> None:
        self.pasta_saida = Path(pasta_saida)

    @staticmethod
    def _ler_planilha(planilha: str | Path) -> pd.DataFrame:
        origem = Path(planilha)
        extensao = origem.suffix.lower()
        if extensao in {".csv", ".tsv", ".txt"}:
            separador = "\t" if extensao == ".tsv" else (None if extensao == ".txt" else ",")
            if separador is None:
                return pd.read_csv(origem, sep=None, engine="python")
            return pd.read_csv(origem, sep=separador)
        if extensao in {".xlsx", ".xls", ".xlsm", ".xlsb", ".ods"}:
            return pd.read_excel(origem)
        if extensao in {".json", ".jsonl", ".ndjson"}:
            return pd.read_json(origem, lines=extensao in {".jsonl", ".ndjson"})
        if extensao == ".parquet":
            return pd.read_parquet(origem)
        if extensao == ".feather":
            return pd.read_feather(origem)
        if extensao == ".html":
            tabelas = pd.read_html(origem)
            if not tabelas:
                raise ValueError("O arquivo HTML não contém tabelas legíveis.")
            return tabelas[0]
        raise ValueError(
            "Formato não suportado. Aceitos: CSV, TSV, TXT, Excel (XLS/XLSX/XLSM/XLSB/ODS), "
            "JSON/JSONL, Parquet, Feather e HTML."
        )

    @staticmethod
    def _validar_data(dados: pd.DataFrame, coluna_data: str) -> pd.DataFrame:
        if coluna_data not in dados.columns:
            raise ValueError(f"A planilha precisa conter a coluna de data '{coluna_data}'.")
        dados = dados.copy()
        dados[coluna_data] = pd.to_datetime(dados[coluna_data], errors="coerce")
        if dados[coluna_data].isna().any():
            raise ValueError("A coluna de data contém valores vazios ou inválidos.")
        return dados.sort_values(coluna_data, kind="stable").reset_index(drop=True)

    def dividir_base(
        self,
        planilha: str | Path,
        porcentagem_x: float = 70,
        porcentagem_y: float = 15,
        porcentagem_z: float = 15,
        coluna_data: str = "Data",
    ) -> tuple[Path, Path, Path]:
        """Salva X (inicial), Y (intermediária) e Z (final), sem aleatoriedade."""
        partes_pct = (porcentagem_x, porcentagem_y, porcentagem_z)
        if any(p < 0 for p in partes_pct) or abs(sum(partes_pct) - 100) >= 1e-9:
            raise ValueError("As porcentagens devem ser não negativas e somar 100.")

        origem = Path(planilha)
        dados = self._validar_data(self._ler_planilha(origem), coluna_data)
        total = len(dados)
        corte_x = int(total * porcentagem_x / 100)
        corte_y = int(total * (porcentagem_x + porcentagem_y) / 100)
        fatias = (dados.iloc[:corte_x], dados.iloc[corte_x:corte_y], dados.iloc[corte_y:])

        self.pasta_saida.mkdir(parents=True, exist_ok=True)
        caminhos = tuple(
            self.pasta_saida / f"{origem.stem}_{nome}.xlsx" for nome in ("X", "Y", "Z")
        )
        for fatia, caminho in zip(fatias, caminhos):
            fatia.to_excel(caminho, index=False)
        return caminhos

    @staticmethod
    def _nome_coluna(dados: pd.DataFrame, indice_coluna: int) -> str:
        if not isinstance(indice_coluna, int) or isinstance(indice_coluna, bool):
            raise TypeError("O número da coluna deve ser um inteiro baseado em zero.")
        if indice_coluna < 0 or indice_coluna >= len(dados.columns):
            raise IndexError("O número da coluna está fora dos limites da planilha.")
        return str(dados.columns[indice_coluna])

    def ajustar_min_max(
        self,
        planilha_treino: str | Path,
        indice_coluna: int,
        nome_coluna_saida: str | None = None,
        destino: str | Path | None = None,
    ) -> dict[str, Any]:
        """Calcula Min–Max no treino e devolve os parâmetros reutilizáveis.

        ``indice_coluna`` começa em zero. O ajuste usa somente a planilha de
        treino fornecida. Por padrão, a coluna normalizada recebe o sufixo
        ``_MinMax``; os dados originais permanecem na planilha de saída.
        """
        origem = Path(planilha_treino)
        dados = self._ler_planilha(origem)
        coluna = self._nome_coluna(dados, indice_coluna)
        valores = pd.to_numeric(dados[coluna], errors="coerce")
        validos = valores.dropna()
        if validos.empty:
            raise ValueError(f"A coluna '{coluna}' não contém valores numéricos válidos.")
        minimo, maximo = float(validos.min()), float(validos.max())
        if minimo == maximo:
            raise ValueError(
                f"A coluna '{coluna}' é constante no treino; x_max - x_min é zero."
            )

        parametros: dict[str, Any] = {
            "coluna": coluna,
            "nome_coluna_saida": nome_coluna_saida or f"{coluna}_MinMax",
            "minimo_treino": minimo,
            "maximo_treino": maximo,
            "formula": "(x - minimo_treino) / (maximo_treino - minimo_treino)",
        }
        arquivo = self.aplicar_min_max(planilha_treino, parametros, destino)
        parametros["planilha_transformada"] = arquivo
        return parametros

    def aplicar_min_max(
        self,
        planilha: str | Path,
        parametros: dict[str, Any],
        destino: str | Path | None = None,
    ) -> Path:
        """Aplica a escala Min–Max já ajustada, sem recalcular mínimo/máximo."""
        origem = Path(planilha)
        dados = self._ler_planilha(origem)
        coluna = parametros["coluna"]
        if coluna not in dados.columns:
            raise ValueError(f"A planilha não contém a coluna ajustada '{coluna}'.")
        minimo = float(parametros["minimo_treino"])
        maximo = float(parametros["maximo_treino"])
        if maximo == minimo:
            raise ValueError("Os parâmetros informados têm intervalo zero.")
        valores = pd.to_numeric(dados[coluna], errors="coerce")
        dados[parametros["nome_coluna_saida"]] = (valores - minimo) / (maximo - minimo)

        if destino is None:
            destino = self.pasta_saida / f"{origem.stem}_minmax.xlsx"
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        dados.to_excel(destino, index=False)
        return destino


if __name__ == "__main__":
    print("Importe PreparadorBases e use dividir_base, ajustar_min_max ou aplicar_min_max.")
