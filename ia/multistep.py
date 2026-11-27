"""Normalização Min–Max e previsão multistep direta por mínimos quadrados."""

from pathlib import Path

import numpy as np
import pandas as pd

from Bases_para_Treinamento import PreparadorBases


class Multistep:
    def __init__(self, pasta_saida="resultados_multistep"):
        self.preparador = PreparadorBases(Path(pasta_saida) / "normalizados")
        self.escala = None

    @staticmethod
    def _nome_coluna(base, coluna):
        """Aceita o nome da coluna ou sua posição (começando em zero)."""
        if isinstance(coluna, str):
            return coluna
        return base.columns[coluna]

    def normalizar_bases(
        self, treino, validacao, teste,
        coluna_treino, coluna_validacao, coluna_teste,
    ):
        """Ajusta Min–Max no treino e aplica a mesma escala às três bases."""
        bases = [self.preparador._ler_planilha(p) for p in (treino, validacao, teste)]
        colunas = [
            self._nome_coluna(base, coluna)
            for base, coluna in zip(bases, (coluna_treino, coluna_validacao, coluna_teste))
        ]
        if not (colunas[0] == colunas[1] == colunas[2]):
            raise ValueError("Selecione a mesma coluna nas três bases.")

        indice = bases[0].columns.get_loc(colunas[0])
        self.escala = self.preparador.ajustar_min_max(treino, indice)
        treino_norm = self.escala["planilha_transformada"]
        validacao_norm = self.preparador.aplicar_min_max(validacao, self.escala)
        teste_norm = self.preparador.aplicar_min_max(teste, self.escala)
        return treino_norm, validacao_norm, teste_norm

    def prever_horizonte(self, treino, validacao, teste, dimensao, horizonte):
        """Ajusta MQO para um horizonte e prevê após a última observação.

        Para cada horizonte h, ajusta y[t+h] = b0 + b1*y[t-d+1] + ... + bd*y[t]
        usando apenas treino. Validação e teste são usados como histórico recente.
        """
        if dimensao < 1 or horizonte < 1:
            raise ValueError("Dimensão e horizonte devem ser positivos.")
        coluna = self.escala["nome_coluna_saida"]
        bases = [pd.read_excel(p) for p in (treino, validacao, teste)]
        if any(base.empty for base in bases):
            raise ValueError("Treino, validação e teste precisam ter dados.")
        if all("Data" in base.columns for base in bases):
            datas = [pd.to_datetime(base["Data"], errors="coerce") for base in bases]
            if any(d.isna().any() or not d.is_monotonic_increasing for d in datas):
                raise ValueError("As datas das três bases devem estar em ordem crescente.")
            if not (
                datas[0].iloc[-1] < datas[1].iloc[0]
                and datas[1].iloc[-1] < datas[2].iloc[0]
            ):
                raise ValueError("As bases devem seguir a ordem temporal treino, validação e teste.")
        serie = [base[coluna].to_numpy(dtype=float) for base in bases]
        treino_valores = serie[0]

        # Cada linha contém d valores passados e uma coluna de intercepto.
        X, y = [], []
        for alvo in range(dimensao + horizonte - 1, len(treino_valores)):
            inicio = alvo - horizonte - dimensao + 1
            X.append(list(treino_valores[inicio:inicio + dimensao]) + [1.0])
            y.append(treino_valores[alvo])
        if not X:
            raise ValueError("A base de treino é pequena para essa dimensão e horizonte.")

        coeficientes = np.linalg.pinv(np.asarray(X)) @ np.asarray(y)
        historico = np.concatenate(serie)
        janela = list(historico[-dimensao:]) + [1.0]
        return float(np.asarray(janela) @ coeficientes)

    def Modelo_multistep(
        self, treino, validacao, teste,
        coluna_treino, coluna_validacao, coluna_teste,
        dimensao, horizonte,
    ):
        """Normaliza, ajusta um modelo para cada horizonte e retorna previsões.

        O array retornado contém [t+1, t+2, ..., t+horizonte] na escala original.
        """
        bases = self.normalizar_bases(
            treino, validacao, teste,
            coluna_treino, coluna_validacao, coluna_teste,
        )
        previsoes_norm = [
            self.prever_horizonte(*bases, dimensao, h)
            for h in range(1, horizonte + 1)
        ]
        minimo = self.escala["minimo_treino"]
        maximo = self.escala["maximo_treino"]
        return np.asarray(previsoes_norm) * (maximo - minimo) + minimo


if __name__ == "__main__":
    print("Importe a classe Multistep do módulo Multistep.")
