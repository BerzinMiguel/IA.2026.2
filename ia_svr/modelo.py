"""SVR educacional: previsão de fechamento e classificação demonstrativa."""
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from sklearn.metrics import mean_absolute_error, mean_squared_error

COLUNAS = ['dolar', 'bolsa', 'volatilidade']

def recomendar(preco_atual: float, preco_previsto: float, limiar: float = 0.02) -> dict:
    """Classificação ilustrativa; não constitui aconselhamento financeiro."""
    if preco_atual <= 0 or not np.isfinite([preco_atual, preco_previsto]).all():
        raise ValueError('Preços devem ser finitos e o atual positivo.')
    variacao = (preco_previsto / preco_atual) - 1
    acao = 'APLICAR' if variacao > limiar else 'RETIRAR' if variacao < -limiar else 'MANTER'
    return {'recomendacao': acao, 'variacao_prevista_pct': round(100 * variacao, 3),
            'aviso': 'Demonstração acadêmica; não usar para decisões financeiras reais.'}

class ModeloSVR:
    def __init__(self):
        self.pipeline = make_pipeline(StandardScaler(), SVR(kernel='rbf', C=10, epsilon=0.1))
        self.treinado = False

    def treinar(self, dados: pd.DataFrame, pasta_saida='resultados') -> dict:
        """Treina com indicadores observados em t para prever bolsa em t+1.
        NÃO equivale ao treino com previsões multistep out-of-sample.
        """
        df = dados.copy()
        obrigatorias = ['Data'] + COLUNAS
        ausentes = set(obrigatorias) - set(df.columns)
        if ausentes:
            raise ValueError(f'Colunas ausentes: {sorted(ausentes)}')
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
        for col in COLUNAS:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=obrigatorias).sort_values('Data').drop_duplicates('Data', keep='last')
        df = df[(df[COLUNAS] > 0).all(axis=1)].copy()
        df['alvo'] = df['bolsa'].shift(-1)
        df['data_alvo'] = df['Data'].shift(-1)
        df = df.dropna(subset=['alvo'])
        if len(df) < 40:
            raise ValueError('São necessários pelo menos 41 dias de dados alinhados e válidos.')
        corte = int(len(df) * .8)
        treino, teste = df.iloc[:corte], df.iloc[corte:]
        self.pipeline.fit(treino[COLUNAS], treino['alvo'])
        previsto = self.pipeline.predict(teste[COLUNAS])
        real = teste['alvo'].to_numpy()
        metricas = {
            'amostras_treino': len(treino), 'amostras_teste': len(teste),
            'MAE': float(mean_absolute_error(real, previsto)),
            'RMSE': float(np.sqrt(mean_squared_error(real, previsto))),
            'MAPE_pct': float(np.mean(np.abs((real - previsto) / real)) * 100),
            'observacao': 'Avaliação cronológica com entradas reais, não previsões multistep.'
        }
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
        valores = np.array([[dolar, bolsa, volatilidade]], dtype=float)
        if not np.isfinite(valores).all() or (valores <= 0).any():
            raise ValueError('Indicadores precisam ser positivos e finitos.')
        previsao = float(self.pipeline.predict(pd.DataFrame(valores, columns=COLUNAS))[0])
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
        self.pipeline = joblib.load(caminho)
        self.treinado = True
        return self
