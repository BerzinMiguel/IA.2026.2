"""Etapa 5: o sistema lógico de decisão com a posição do usuário."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ia.decisao import (  # noqa: E402
    ALTA, APLICAR, APLICAR_MAIS, BAIXA, MANTER, RETIRAR, SEM_SINAL,
    avaliar_posicao, classificar, classificar_sinal,
)

POSICAO = {"quantidade": 100, "cotacao_entrada": 38.50}


class TestClassificacao(unittest.TestCase):
    def test_matriz_do_professor(self):
        """As quatro classes pedidas, nas seis combinações possíveis."""
        casos = [
            (ALTA, False, APLICAR),
            (ALTA, True, APLICAR_MAIS),
            (BAIXA, True, RETIRAR),
            (BAIXA, False, MANTER),       # sem posição não se manda retirar
            (SEM_SINAL, True, MANTER),
            (SEM_SINAL, False, MANTER),
        ]
        for sinal, tem_posicao, esperado in casos:
            with self.subTest(sinal=sinal, tem_posicao=tem_posicao):
                self.assertEqual(classificar(sinal, tem_posicao), esperado)

    def test_nunca_manda_retirar_sem_posicao(self):
        for sinal in (ALTA, BAIXA, SEM_SINAL):
            self.assertNotEqual(classificar(sinal, False), RETIRAR)

    def test_banda_de_indiferenca(self):
        self.assertEqual(classificar_sinal(2.5, 2.0), ALTA)
        self.assertEqual(classificar_sinal(-2.5, 2.0), BAIXA)
        self.assertEqual(classificar_sinal(1.9, 2.0), SEM_SINAL)
        self.assertEqual(classificar_sinal(-2.0, 2.0), SEM_SINAL)  # limite fechado


class TestAvaliarPosicao(unittest.TestCase):
    def test_sem_posicao_nao_traz_valores(self):
        r = avaliar_posicao(preco_atual=44.02, preco_previsto=44.16)
        self.assertFalse(r["tem_posicao"])
        self.assertIsNone(r["posicao"])
        self.assertEqual(r["recomendacao"], MANTER)
        self.assertEqual(r["sinal"], SEM_SINAL)

    def test_resultado_da_posicao(self):
        r = avaliar_posicao(preco_atual=44.02, preco_previsto=44.16, **POSICAO)
        p = r["posicao"]
        self.assertEqual(p["valor_investido"], 3850.0)
        self.assertEqual(p["valor_atual"], 4402.0)
        self.assertAlmostEqual(p["resultado_atual"], 552.0, places=2)
        self.assertAlmostEqual(p["resultado_atual_pct"], 14.338, places=2)
        self.assertAlmostEqual(p["ganho_previsto_periodo"], 14.0, places=0)

    def test_valor_investido_equivale_a_quantidade(self):
        por_qtd = avaliar_posicao(preco_atual=44.02, preco_previsto=44.16, **POSICAO)
        por_valor = avaliar_posicao(preco_atual=44.02, preco_previsto=44.16,
                                    valor_investido=3850.0, cotacao_entrada=38.50)
        self.assertEqual(por_qtd["posicao"], por_valor["posicao"])

    def test_faixa_de_erro(self):
        r = avaliar_posicao(preco_atual=44.02, preco_previsto=44.16,
                            erro_modelo=0.8545, **POSICAO)
        self.assertEqual(r["faixa_preco"], [43.3055, 45.0145])
        self.assertEqual(r["posicao"]["faixa_valor"], [4330.55, 4501.45])
        # O erro do modelo é maior que o movimento previsto: isso tem de aparecer.
        self.assertGreater(r["erro_modelo_pct"], abs(r["variacao_prevista_pct"]))

    def test_retirar_distingue_lucro_de_prejuizo(self):
        lucro = avaliar_posicao(preco_atual=44.02, preco_previsto=40.0, **POSICAO)
        self.assertEqual(lucro["recomendacao"], RETIRAR)
        self.assertEqual(lucro["motivo_retirada"], "realizar lucro")

        prejuizo = avaliar_posicao(preco_atual=44.02, preco_previsto=30.0,
                                   quantidade=100, cotacao_entrada=50.0)
        self.assertEqual(prejuizo["recomendacao"], RETIRAR)
        self.assertEqual(prejuizo["motivo_retirada"], "limitar prejuízo")

    def test_preco_de_entrada_nao_muda_a_recomendacao(self):
        """Custo irrecuperável: onde a pessoa entrou não altera a decisão."""
        base = dict(preco_atual=44.02, preco_previsto=46.5, quantidade=100)
        no_lucro = avaliar_posicao(**base, cotacao_entrada=10.0)
        no_prejuizo = avaliar_posicao(**base, cotacao_entrada=90.0)
        self.assertEqual(no_lucro["recomendacao"], no_prejuizo["recomendacao"])
        self.assertEqual(no_lucro["sinal"], no_prejuizo["sinal"])

    def test_entradas_invalidas(self):
        for kwargs in (
            {"preco_atual": 0, "preco_previsto": 44.0},
            {"preco_atual": 44.0, "preco_previsto": -1},
            {"preco_atual": 44.0, "preco_previsto": 44.0, "quantidade": -5},
            {"preco_atual": 44.0, "preco_previsto": 44.0, "quantidade": 10},
            {"preco_atual": 44.0, "preco_previsto": 44.0, "valor_investido": 100},
            {"preco_atual": float("nan"), "preco_previsto": 44.0},
        ):
            with self.subTest(**kwargs):
                with self.assertRaises(ValueError):
                    avaliar_posicao(**kwargs)


if __name__ == "__main__":
    unittest.main()
