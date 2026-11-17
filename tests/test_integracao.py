import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import pandas as pd
from ia.multistep import Multistep
from ia.svr import PipelineIntegrado, recomendar
from ia.svr.integracao import carregar_bases


def bases(n=90):
    t = np.arange(n)
    datas = pd.bdate_range("2024-01-01", periods=n)
    return tuple(pd.DataFrame({"Data": datas, coluna: valores}) for coluna, valores in (
        ("Valor", 5 + t * .001 + np.sin(t / 4) * .02),
        ("Valor", 30 + t * .02 + np.cos(t / 7) * .3),
        ("Volatilidade_Diaria", .2 + np.sin(t / 3) ** 2)))


class TestIntegracao(unittest.TestCase):
    def pipeline(self):
        return PipelineIntegrado(dimensao=3, horizonte=2, minimo_treino=20)

    def test_fluxo_completo_e_persistencia(self):
        with TemporaryDirectory() as pasta:
            caminhos = []
            for nome, df in zip(("dolar", "bolsa", "vol"), bases()):
                caminho = Path(pasta) / f"{nome}.xlsx"
                df.to_excel(caminho, index=False)
                caminhos.append(caminho)
            pipe = self.pipeline()
            metricas = pipe.treinar(*caminhos, pasta_saida=pasta)
            resposta = pipe.prever()
            json.dumps(resposta, allow_nan=False)
            self.assertEqual(len(resposta["previsoes"]), 2)
            self.assertIsNone(resposta["data_alvo"])
            self.assertIn(resposta["recomendacao"], ("APLICAR", "MANTER", "RETIRAR"))
            self.assertEqual(resposta, PipelineIntegrado.carregar(Path(pasta) / "pipeline.joblib").prever())
            self.assertEqual(metricas.keys(), {"1", "2"})
            self.assertTrue((Path(pasta) / "avaliacao_svr.csv").exists())
            for h in (1, 2):
                m = metricas[str(h)]
                self.assertLess(m["ultimo_alvo_treino"], m["primeira_origem_teste"])
            ultimo = pd.Timestamp(resposta["data_atualizacao"])
            datas = pd.bdate_range(ultimo + pd.offsets.Day(1), periods=2)
            self.assertEqual(pipe.prever(datas)["data_alvo"], datas[0].date().isoformat())
            for invalidas in ([ultimo], [ultimo, ultimo], [datas[1], datas[0]], [datas[0], pd.NaT]):
                with self.assertRaises(ValueError):
                    pipe.prever(invalidas)

    def test_oos_nao_depende_do_futuro(self):
        originais = bases()
        dados, _ = carregar_bases(*originais)
        mudados = dados.copy()
        mudados.loc[50:, ["dolar", "bolsa", "volatilidade"]] *= 10
        pipe = self.pipeline()
        a = pipe.gerar_historico(dados)
        b = pipe.gerar_historico(mudados)
        passado = a.origem < dados.iloc[50].Data
        pd.testing.assert_frame_equal(a.loc[passado, ["dolar", "bolsa", "volatilidade"]],
                                      b.loc[passado, ["dolar", "bolsa", "volatilidade"]])
        # Dados de teste não influenciam o ajuste do scaler/SVR.
        pipe.treinar(*originais)
        alteradas = tuple(df.copy() for df in originais)
        for df in alteradas:
            df.loc[df.Data >= pipe.limite_treino, df.columns[1]] *= 2
        outro = self.pipeline()
        outro.treinar(*alteradas)
        for h in (1, 2):
            x = pd.DataFrame([[5., 31., .5]], columns=["dolar", "bolsa", "volatilidade"])
            np.testing.assert_array_equal(pipe.modelos[h].predict(x), outro.modelos[h].predict(x))

    def test_paridade_com_modelo_ryan(self):
        with TemporaryDirectory() as pasta:
            serie = bases(50)[0]
            caminhos = []
            for nome, parte in zip(("X", "Y", "Z"), (serie.iloc[:30], serie.iloc[30:40], serie.iloc[40:])):
                caminho = Path(pasta) / f"{nome}.xlsx"
                parte.to_excel(caminho, index=False)
                caminhos.append(caminho)
            original = Multistep(Path(pasta) / "norm").Modelo_multistep(*caminhos, 1, 1, 1, 3, 2)
            memoria = Multistep.prever_serie(serie.Valor.iloc[:30], serie.Valor, 3, 2)
            np.testing.assert_allclose(original, memoria, rtol=1e-9)

    def test_alinhamento_e_zero_volatilidade(self):
        a, b, c = bases()
        c.loc[0, "Volatilidade_Diaria"] = np.nan
        c.loc[1, "Volatilidade_Diaria"] = 0
        dados, avisos = carregar_bases(a, b.iloc[1:], c)
        self.assertEqual(len(dados), 89)
        self.assertEqual(dados.iloc[0].volatilidade, 0)
        self.assertTrue(avisos)

    def test_erros_de_entrada(self):
        a, b, c = bases()
        casos = [a.drop(columns="Valor"), pd.concat([a, a.iloc[:1]]),
                 a.assign(Valor=np.inf), a.assign(Valor=-1), a.assign(Data="invalida")]
        for invalido in casos:
            with self.subTest():
                with self.assertRaises(ValueError):
                    carregar_bases(invalido, b, c)
        with self.assertRaises(FileNotFoundError):
            carregar_bases("nao_existe.xlsx", b, c)
        with self.assertRaises(ValueError):
            carregar_bases(a, b.assign(Data=b.Data.map(lambda data: data + pd.offsets.Day(1000))), c)
        with self.assertRaises(ValueError):
            self.pipeline().treinar(*bases(25))
        with self.assertRaises(ValueError):
            self.pipeline().treinar(a.assign(Valor=5), b, c)
        with self.assertRaises(RuntimeError):
            self.pipeline().prever()
        with self.assertRaises(ValueError):
            PipelineIntegrado(horizonte=0)
        with TemporaryDirectory() as pasta:
            import joblib
            caminho = Path(pasta) / "incompativel.joblib"
            joblib.dump({}, caminho)
            with self.assertRaises(ValueError):
                PipelineIntegrado.carregar(caminho)

    def test_cli_e_importacao_sem_efeito_colateral(self):
        import subprocess
        import sys
        raiz = Path(__file__).resolve().parents[1]
        falha = subprocess.run([sys.executable, "scripts/treinar_svr.py"], cwd=raiz,
                               capture_output=True, text=True)
        self.assertEqual(falha.returncode, 2)
        with TemporaryDirectory() as pasta:
            pipe = self.pipeline()
            pipe.treinar(*bases(), pasta_saida=pasta)
            resultado = subprocess.run([sys.executable, "scripts/treinar_svr.py", "--carregar",
                                         str(Path(pasta) / "pipeline.joblib")], cwd=raiz,
                                        capture_output=True, text=True, encoding="utf-8",
                                        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
            self.assertEqual(len(json.loads(resultado.stdout)["resultado"]["previsoes"]), 2)
        invalida = bases()[2].astype({"Volatilidade_Diaria": object})
        invalida.iloc[0, 1] = "texto"
        with self.assertRaises(ValueError):
            carregar_bases(*bases()[:2], invalida)

    def test_limites_recomendacao(self):
        self.assertEqual(recomendar(100, 102)["recomendacao"], "MANTER")
        self.assertEqual(recomendar(100, 98)["recomendacao"], "MANTER")
        for limiar in (-1, float("nan")):
            with self.assertRaises(ValueError):
                recomendar(100, 102, limiar)


if __name__ == "__main__":
    unittest.main()
