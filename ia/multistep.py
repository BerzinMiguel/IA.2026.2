"""Normalização Min–Max e previsão multistep direta por mínimos quadrados."""

from pathlib import Path

import numpy as np
import pandas as pd

from ia.bases import PreparadorBases


class Multistep:
    def __init__(self, pasta_saida="resultados_multistep"):
        self.preparador = PreparadorBases(Path(pasta_saida) / "normalizados")
        self.escala = None

    @staticmethod
    def prever_serie(treino, historico, dimensao, horizonte):
        """MQO direto em memória; escala e coeficientes usam só treino.

        Retorna [t+1,...,t+H] na unidade original. O chamador garante
        que treino e histórico contêm apenas observações disponíveis em t.
        """
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 1
               for v in (dimensao, horizonte)):
            raise ValueError("Dimensão e horizonte devem ser inteiros positivos.")
        treino = np.asarray(treino, dtype=float)
        historico = np.asarray(historico, dtype=float)
        if treino.ndim != 1 or historico.ndim != 1:
            raise ValueError("Esperadas séries unidimensionais.")
        if len(treino) < dimensao + horizonte or len(historico) < dimensao:
            raise ValueError("Histórico insuficiente para dimensão e horizonte.")
        if not np.isfinite(treino).all() or not np.isfinite(historico).all():
            raise ValueError("Séries devem conter somente valores finitos.")
        minimo, maximo = PreparadorBases.limites_min_max(treino)
        if minimo == maximo:
            raise ValueError("Série constante no treino: escala Min-Max indefinida.")
        serie = PreparadorBases.normalizar_valores(treino, minimo, maximo)
        janela = np.r_[PreparadorBases.normalizar_valores(historico[-dimensao:], minimo, maximo), 1.0]
        previsoes = []
        for h in range(1, horizonte + 1):
            coeficientes = Multistep._ajustar_mqo(serie, dimensao, h)
            previsoes.append(float(janela @ coeficientes))
        resultado = np.asarray(previsoes) * (maximo - minimo) + minimo
        if not np.isfinite(resultado).all():
            raise ValueError("Multistep produziu previsão não finita.")
        return resultado

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
        coeficientes = self._ajustar_mqo(serie[0], dimensao, horizonte)
        historico = np.concatenate(serie)
        janela = list(historico[-dimensao:]) + [1.0]
        return float(np.asarray(janela) @ coeficientes)

    @staticmethod
    def _ajustar_mqo(treino_valores, dimensao, horizonte):
        # Cada linha contém d valores passados e uma coluna de intercepto.
        X, y = [], []
        for alvo in range(dimensao + horizonte - 1, len(treino_valores)):
            inicio = alvo - horizonte - dimensao + 1
            X.append(list(treino_valores[inicio:inicio + dimensao]) + [1.0])
            y.append(treino_valores[alvo])
        if not X:
            raise ValueError("A base de treino é pequena para essa dimensão e horizonte.")

        return np.linalg.pinv(np.asarray(X)) @ np.asarray(y)

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
