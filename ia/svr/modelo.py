"""SVR educacional: previsão de fechamento e classificação demonstrativa."""
from dataclasses import dataclass
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import ParameterGrid
from sklearn.svm import SVR
from sklearn.metrics import mean_absolute_error, mean_squared_error

from ia.bases import PreparadorBases

ENTRADAS_SVR = ("dolar", "volatilidade")
GRADE_RBF = {
    "C": 10.0 ** np.arange(-2, 3),
    "gamma": 10.0 ** np.arange(-5, 3),
    "epsilon": 10.0 ** np.arange(-4, -1),
}


@dataclass
class SVRTreinado:
    estimador: SVR
    entradas: tuple[str, ...]
    minimo: pd.Series
    maximo: pd.Series
    mse_validacao: float

    def predict(self, dados):
        valores = dados.loc[:, list(self.entradas)].to_numpy(dtype=float)
        if not np.isfinite(valores).all():
            raise ValueError("As entradas do SVR devem ser finitas.")
        escala = PreparadorBases.normalizar_valores(
            valores, self.minimo.to_numpy(), self.maximo.to_numpy()
        )
        return self.estimador.predict(escala)


def dividir_base_svr(dados, proporcoes=(60, 20, 20)):
    datas = PreparadorBases._validar_data(dados, "data_alvo")
    treino, validacao, teste = PreparadorBases.dividir_dados(datas, proporcoes, "origem")
    for parte in (treino, validacao, teste):
        if parte["data_alvo"].le(parte["origem"]).any():
            raise ValueError("A data-alvo deve ser posterior à origem.")
    if pd.concat([treino["origem"], validacao["origem"], teste["origem"]]).duplicated().any():
        raise ValueError("Informe apenas uma amostra por origem para cada horizonte.")
    if validacao.empty or teste.empty:
        raise ValueError("Validação e teste precisam conter amostras.")
    inicio_validacao = validacao["origem"].iloc[0]
    inicio_teste = teste["origem"].iloc[0]
    treino = treino[treino["data_alvo"] < inicio_validacao]
    validacao = validacao[validacao["data_alvo"] < inicio_teste]
    if treino.empty or validacao.empty:
        raise ValueError("Treino ou validação sem amostras após a separação temporal.")
    return treino, validacao, teste


def treinar_svr(treino, validacao, parametros=None, entradas=ENTRADAS_SVR, alvo="alvo"):
    """Ajusta Min–Max no treino e seleciona o SVR com menor MSE em reais."""
    colunas = list(entradas)
    if not colunas or len(set(colunas)) != len(colunas) or alvo in colunas:
        raise ValueError("Informe entradas distintas e um alvo separado.")
    x_treino = treino[colunas].astype(float)
    x_validacao = validacao[colunas].astype(float)
    y_treino = treino[alvo].to_numpy(dtype=float)
    y_validacao = validacao[alvo].to_numpy(dtype=float)
    minimo, maximo = PreparadorBases.limites_min_max(x_treino)
    # Colunas constantes ficam em zero no treino, com intervalo unitário.
    maximo = maximo.where(maximo != minimo, minimo + 1)
    x = PreparadorBases.normalizar_valores(x_treino, minimo, maximo).to_numpy()
    x_val = PreparadorBases.normalizar_valores(x_validacao, minimo, maximo).to_numpy()
    grade = GRADE_RBF if parametros is None else {
        chave: np.atleast_1d(valor).tolist() for chave, valor in parametros.items()
    }
    melhor = None
    menor_mse = np.inf
    for combinacao in ParameterGrid(grade):
        estimador = SVR(kernel="rbf", **combinacao).fit(x, y_treino)
        mse = mean_squared_error(y_validacao, estimador.predict(x_val))
        if mse < menor_mse:
            melhor, menor_mse = estimador, mse
    return SVRTreinado(melhor, tuple(colunas), minimo, maximo, menor_mse)


def prever_ativo(modelo, dolar_previsto, volatilidade_prevista):
    """Retorna o fechamento em reais a partir dos dois valores previstos."""
    dados = pd.DataFrame({"dolar": [dolar_previsto], "volatilidade": [volatilidade_prevista]})
    return float(modelo.predict(dados)[0])


def avaliar_svr(modelo, teste, alvo="alvo"):
    real = teste[alvo].to_numpy(dtype=float)
    previsto = modelo.predict(teste)
    mse = float(mean_squared_error(real, previsto))
    nao_zero = real != 0
    mape = (float(np.mean(np.abs((real[nao_zero] - previsto[nao_zero]) / real[nao_zero])) * 100)
            if nao_zero.any() else None)
    return previsto, {
        "MSE": mse,
        "MAE": float(mean_absolute_error(real, previsto)),
        "RMSE": float(np.sqrt(mse)),
        "MAPE_pct": mape,
    }

def recomendar(preco_atual: float, preco_previsto: float, limiar: float = 0.02) -> dict:
    """Classificação ilustrativa; não constitui aconselhamento financeiro."""
    if preco_atual <= 0 or not np.isfinite([preco_atual, preco_previsto]).all():
        raise ValueError('Preços devem ser finitos e o atual positivo.')
    if not np.isfinite(limiar) or limiar < 0:
        raise ValueError('Limiar deve ser finito e não negativo.')
    variacao = (preco_previsto - preco_atual) / preco_atual
    acao = 'APLICAR' if variacao > limiar else 'RETIRAR' if variacao < -limiar else 'MANTER'
    return {'recomendacao': acao, 'variacao_prevista_pct': round(100 * variacao, 3),
            'aviso': 'Demonstração acadêmica; não usar para decisões financeiras reais.'}

class ModeloSVR:
    def __init__(self):
        self.pipeline = None
        self.treinado = False

    def treinar(self, dados: pd.DataFrame, pasta_saida='resultados') -> dict:
        """Treina com indicadores observados em t para prever bolsa em t+1.
        NÃO equivale ao treino com previsões multistep out-of-sample.
        """
        df = dados.copy()
        obrigatorias = ['Data', 'bolsa', *ENTRADAS_SVR]
        ausentes = set(obrigatorias) - set(df.columns)
        if ausentes:
            raise ValueError(f'Colunas ausentes: {sorted(ausentes)}')
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
        for col in obrigatorias[1:]:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=obrigatorias).sort_values('Data').drop_duplicates('Data', keep='last')
        df = df[((df[['dolar', 'bolsa']] > 0).all(axis=1) & (df['volatilidade'] >= 0))].copy()
        df['alvo'] = df['bolsa'].shift(-1)
        df['data_alvo'] = df['Data'].shift(-1)
        df = df.dropna(subset=['alvo'])
        if len(df) < 40:
            raise ValueError('São necessários pelo menos 41 dias de dados alinhados e válidos.')
        treino, validacao, teste = dividir_base_svr(df.rename(columns={"Data": "origem"}))
        self.pipeline = treinar_svr(treino, validacao)
        previsto, metricas = avaliar_svr(self.pipeline, teste)
        real = teste["alvo"].to_numpy()
        metricas.update(amostras_treino=len(treino), amostras_teste=len(teste),
                        observacao="Avaliação cronológica do modelo independente.")
        saida = Path(pasta_saida)
        saida.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({'data_alvo': teste['data_alvo'].dt.strftime('%Y-%m-%d'),
                      'real': real, 'previsto': previsto,
                      'erro': real - previsto}).to_csv(saida / 'avaliacao_svr.csv', index=False)
        (saida / 'metricas_svr.json').write_text(json.dumps(metricas, indent=2, ensure_ascii=False), encoding='utf-8')
        self.treinado = True
        return metricas

    def prever(self, dolar: float, bolsa: float, volatilidade: float) -> dict:
        if not self.treinado:
            raise RuntimeError('Treine ou carregue o modelo antes de prever.')
        previsao = prever_ativo(self.pipeline, dolar, volatilidade)
        return {'fechamento_previsto': round(previsao, 4),
                **recomendar(bolsa, previsao)}

    def salvar(self, caminho='resultados/modelo_svr.joblib'):
        if not self.treinado:
            raise RuntimeError('Não há modelo treinado.')
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.pipeline, caminho)

    def carregar(self, caminho='resultados/modelo_svr.joblib'):
        # Carregue apenas arquivos gerados pelo próprio projeto e de origem confiável.
        modelo = joblib.load(caminho)
        if not isinstance(modelo, SVRTreinado):
            raise ValueError("Artefato SVR incompatível. Treine e salve o modelo novamente.")
        self.pipeline = modelo
        self.treinado = True
        return self
