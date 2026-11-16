import unittest
import numpy as np
import pandas as pd
from tempfile import TemporaryDirectory
from ia_svr.modelo import ModeloSVR, recomendar

class TestSVR(unittest.TestCase):
    def test_recomendacoes(self):
        self.assertEqual(recomendar(100, 105)['recomendacao'], 'APLICAR')
        self.assertEqual(recomendar(100, 95)['recomendacao'], 'RETIRAR')
        self.assertEqual(recomendar(100, 101)['recomendacao'], 'MANTER')

    def test_treino_e_previsao(self):
        rng = np.random.default_rng(42)
        n = 100
        dados = pd.DataFrame({'Data': pd.bdate_range('2025-01-01', periods=n),
                              'dolar': 5 + rng.random(n),
                              'bolsa': 20 + np.arange(n) * .02 + rng.random(n),
                              'volatilidade': 15 + rng.random(n)})
        with TemporaryDirectory() as pasta:
            modelo = ModeloSVR()
            metricas = modelo.treinar(dados, pasta)
            self.assertGreater(metricas['amostras_teste'], 0)
            modelo.salvar(f'{pasta}/modelo.joblib')
            novo = ModeloSVR().carregar(f'{pasta}/modelo.joblib')
            self.assertIn('fechamento_previsto', novo.prever(5.5, 21, 15.5))

if __name__ == '__main__':
    unittest.main()
