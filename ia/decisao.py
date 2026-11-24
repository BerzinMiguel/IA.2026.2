"""Sistema lógico de decisão (Etapa 5), com a posição do usuário.

Regra pedida pelo professor: perguntar primeiro se a pessoa já tem dinheiro
investido na ação. A classificação sai do cruzamento dessa informação com a
previsão do modelo:

        sem posição + alta     -> APLICAR
        sem posição + baixa    -> MANTER      (não faz sentido mandar retirar
        sem posição + sem sinal-> MANTER       quem não tem posição)
        com posição + alta     -> APLICAR MAIS
        com posição + baixa    -> RETIRAR
        com posição + sem sinal-> MANTER

O campo `sinal` viaja separado da recomendação justamente porque `MANTER`
aparece por dois motivos diferentes: o modelo prever queda para quem não tem
posição, ou o modelo não ter nada a dizer. A tela precisa distinguir os dois.

`sem sinal` não é um detalhe de interface. A variação prevista só carrega
informação quando supera o erro típico do próprio modelo: com MAE de R$ 0,85
sobre um preço de R$ 44, qualquer previsão menor que ~1,9% está dentro do
ruído. O limiar de 2% já usado na decisão fica, por coincidência, nesse nível.

O preço de entrada NUNCA entra na decisão, só no relato de resultado. Decidir
segurar porque está no prejuízo (ou vender porque está no lucro) é a falácia
do custo irrecuperável: o que importa é a previsão, não onde a pessoa entrou.
"""
from __future__ import annotations

import math

APLICAR = "APLICAR"
APLICAR_MAIS = "APLICAR MAIS"
MANTER = "MANTER"
RETIRAR = "RETIRAR"

ALTA, BAIXA, SEM_SINAL = "alta", "baixa", "sem_sinal"

AVISO_SEM_SINAL = (
    "Variação prevista dentro do erro típico do modelo: ele não distingue "
    "alta de baixa neste horizonte."
)
AVISO_CUSTO_IRRECUPERAVEL = (
    "O preço de entrada não influencia a recomendação, apenas o resultado "
    "exibido."
)


def _finito(valor, nome, *, positivo=False, obrigatorio=True):
    if valor is None:
        if obrigatorio:
            raise ValueError(f"{nome} é obrigatório.")
        return None
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{nome} deve ser numérico.") from None
    if not math.isfinite(valor):
        raise ValueError(f"{nome} deve ser finito.")
    if positivo and valor <= 0:
        raise ValueError(f"{nome} deve ser positivo.")
    if not positivo and valor < 0:
        raise ValueError(f"{nome} não pode ser negativo.")
    return valor


def classificar_sinal(variacao_pct: float, limiar_pct: float) -> str:
    """Alta, baixa ou sem sinal, pela banda de indiferença do limiar."""
    if variacao_pct > limiar_pct:
        return ALTA
    if variacao_pct < -limiar_pct:
        return BAIXA
    return SEM_SINAL


def classificar(sinal: str, tem_posicao: bool) -> str:
    """O 2x3 da docstring do módulo: a recomendação em si."""
    if sinal == ALTA:
        return APLICAR_MAIS if tem_posicao else APLICAR
    if sinal == BAIXA and tem_posicao:
        return RETIRAR
    return MANTER


def avaliar_posicao(
    *,
    preco_atual: float,
    preco_previsto: float,
    limiar_pct: float = 2.0,
    quantidade=None,
    cotacao_entrada=None,
    valor_investido=None,
    erro_modelo=None,
    data_alvo=None,
) -> dict:
    """Cruza a posição do usuário com a previsão e devolve a decisão.

    A posição pode vir como `quantidade` de ações ou como `valor_investido`;
    em ambos os casos `cotacao_entrada` é necessária para calcular resultado.
    Sem nenhum dos dois, trata-se de alguém sem posição.

    `erro_modelo` é o MAE em reais; quando informado, a resposta traz a faixa
    de preço e de valor correspondente, para a tela não exibir um ponto seco.
    """
    preco_atual = _finito(preco_atual, "preco_atual", positivo=True)
    preco_previsto = _finito(preco_previsto, "preco_previsto", positivo=True)
    limiar_pct = _finito(limiar_pct, "limiar_pct")
    erro_modelo = _finito(erro_modelo, "erro_modelo", obrigatorio=False)

    quantidade = _finito(quantidade, "quantidade", obrigatorio=False)
    cotacao_entrada = _finito(cotacao_entrada, "cotacao_entrada", positivo=True, obrigatorio=False)
    valor_investido = _finito(valor_investido, "valor_investido", obrigatorio=False)

    if quantidade is None and valor_investido is not None:
        if cotacao_entrada is None:
            raise ValueError("Informe cotacao_entrada junto com valor_investido.")
        quantidade = valor_investido / cotacao_entrada

    tem_posicao = bool(quantidade) and quantidade > 0
    if tem_posicao and cotacao_entrada is None:
        raise ValueError("Informe cotacao_entrada para calcular o resultado da posição.")

    variacao_pct = (preco_previsto / preco_atual - 1) * 100
    sinal = classificar_sinal(variacao_pct, limiar_pct)
    recomendacao = classificar(sinal, tem_posicao)

    resposta = {
        "tem_posicao": tem_posicao,
        "sinal": sinal,
        "recomendacao": recomendacao,
        "data_alvo": data_alvo,
        "preco_atual": round(preco_atual, 4),
        "preco_previsto": round(preco_previsto, 4),
        "variacao_prevista_pct": round(variacao_pct, 3),
        "limiar_pct": round(limiar_pct, 4),
        "avisos": [],
    }

    if erro_modelo is not None:
        resposta["erro_modelo"] = round(erro_modelo, 4)
        resposta["erro_modelo_pct"] = round(100 * erro_modelo / preco_atual, 3)
        resposta["faixa_preco"] = [round(preco_previsto - erro_modelo, 4),
                                   round(preco_previsto + erro_modelo, 4)]

    if sinal == SEM_SINAL:
        resposta["avisos"].append(AVISO_SEM_SINAL)

    if not tem_posicao:
        resposta["posicao"] = None
        return resposta

    valor_investido = quantidade * cotacao_entrada
    valor_atual = quantidade * preco_atual
    valor_previsto = quantidade * preco_previsto
    resposta["posicao"] = {
        "quantidade": round(quantidade, 6),
        "cotacao_entrada": round(cotacao_entrada, 4),
        "valor_investido": round(valor_investido, 2),
        "valor_atual": round(valor_atual, 2),
        "resultado_atual": round(valor_atual - valor_investido, 2),
        "resultado_atual_pct": round(100 * (preco_atual / cotacao_entrada - 1), 3),
        "valor_previsto": round(valor_previsto, 2),
        "resultado_previsto": round(valor_previsto - valor_investido, 2),
        "resultado_previsto_pct": round(100 * (preco_previsto / cotacao_entrada - 1), 3),
        "ganho_previsto_periodo": round(valor_previsto - valor_atual, 2),
    }
    if erro_modelo is not None:
        resposta["posicao"]["faixa_valor"] = [
            round(quantidade * (preco_previsto - erro_modelo), 2),
            round(quantidade * (preco_previsto + erro_modelo), 2),
        ]
    resposta["avisos"].append(AVISO_CUSTO_IRRECUPERAVEL)
    if recomendacao == RETIRAR:
        no_lucro = preco_previsto > cotacao_entrada
        resposta["motivo_retirada"] = "realizar lucro" if no_lucro else "limitar prejuízo"
    return resposta
