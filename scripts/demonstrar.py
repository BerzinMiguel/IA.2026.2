"""Mostra o caminho completo da IA, passo a passo, em um comando.

    python scripts/demonstrar.py                 # usa o ultimo pregao do banco
    python scripts/demonstrar.py --data 2026-09-15
    python scripts/demonstrar.py --sem-explicacao
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import Config  # noqa: E402
from backend.db import connect  # noqa: E402
from backend.services.dados import carregar_historico, datas_disponiveis  # noqa: E402
from ia import adaptador  # noqa: E402

LARGURA = 72

METODO = """
  ENTRADA
    Tres series diarias, alinhadas pela intersecao de datas (um dia so entra
    se existe nas tres). Nenhum dia faltante e preenchido artificialmente.
      dolar          cotacao de venda (PTAX, Banco Central)
      bolsa          fechamento da acao acompanhada
      volatilidade   |ln(Pt / Pt-1)| * 100, associada a data t

  ETAPA 1 - MULTISTEP, um para cada serie
    Regressao linear direta por minimos quadrados sobre os d ultimos valores:
        y[t+h] = b0 + b1*y[t-d+1] + ... + bd*y[t]
    Um modelo por horizonte h, coeficientes por pinv(X) @ y. A normalizacao
    Min-Max e ajustada somente no treino e reaplicada ao resto, para que a
    escala nao carregue informacao de dados futuros.
    Saida: previsao dos tres indicadores para t+1 ... t+H.

  ETAPA 2 - SVR, um para cada horizonte
    Kernel RBF (C=10, epsilon=0.1) sobre StandardScaler.
      entrada  as tres previsoes multistep daquele horizonte
      alvo     o fechamento real da bolsa em t+h
    O treino percorre a serie em janela expansiva: cada origem usa apenas as
    linhas ate ela, inclusive para calcular a escala. A separacao treino/teste
    e temporal e estrita - alvos de treino anteriores a primeira origem de
    teste, sem sobreposicao.

  ETAPA 3 - DECISAO
        variacao = (previsto - atual) / atual
        acima de +limiar  -> aplicar
        abaixo de -limiar -> retirar
        entre os dois     -> manter
    A confianca e a distancia relativa ao limiar, saturada em 1,0. Nao e
    probabilidade: so serve para ordenar dias entre si.

  POR QUE WALK-FORWARD
    Cada execucao recebe do backend apenas o historico ate a data de
    referencia. A previsao do dia 10 e feita com o que existia no dia 10 e
    so depois e comparada ao fechamento real do dia-alvo. Avaliar de outro
    jeito - treinando com a serie toda e medindo no meio dela - produz um
    erro menor e sem significado.
"""

LIMITE = """
  O SVR com kernel RBF nao extrapola acima da faixa de precos que viu no
  treino. Quando o preco sobe para um patamar novo, a previsao fica presa
  perto da media do treino e a recomendacao vira retirar de forma
  sistematica. Treinar apenas com as ultimas N observacoes (IA_MAX_OBS_TREINO)
  reduz muito o efeito, porque aproxima a faixa do treino do preco atual.
  A correcao de fundo e treinar sobre retorno (preco_futuro / preco_atual - 1)
  em vez do nivel do preco.
"""


def titulo(numero, texto):
    print()
    print("=" * LARGURA)
    print(f"{numero}. {texto}")
    print("=" * LARGURA)


def main():
    p = argparse.ArgumentParser(description="Demonstracao do backend de IA")
    p.add_argument("--data", help="data de referencia YYYY-MM-DD")
    p.add_argument("--sem-explicacao", action="store_true",
                   help="pula a descricao do metodo e mostra so o resultado")
    a = p.parse_args()

    conn = connect(Config.DB_PATH)
    data_ref = a.data or datas_disponiveis(conn)[-1]
    historico = carregar_historico(conn, ate=data_ref)
    opcoes = adaptador._opcoes()  # mesma leitura de ambiente que o adaptador faz

    if not a.sem_explicacao:
        titulo(1, "COMO A ANALISE FUNCIONA")
        print(METODO)
        print("  CONFIGURACAO ATIVA NESTA EXECUCAO")
        print(f"    dimensao (lags)        {opcoes['dimensao']}")
        print(f"    horizonte              {opcoes['horizonte']} pregoes")
        print(f"    limiar da decisao      {opcoes['limiar'] * 100:.1f}%")
        print(f"    minimo de treino       {opcoes['minimo_treino']} observacoes")
        janela = opcoes["max_obs"] or "serie inteira"
        print(f"    janela de treino       {janela}")
        print(f"    artefato pre-treinado  {opcoes['artefato'] or 'nenhum, treina agora'}")

    titulo(2, f"ENTRADA: o que a IA enxerga em {data_ref}")
    for nome, serie in historico.items():
        print(f"  {nome:13} {len(serie):5} observacoes   ultimo fechamento: {serie.iloc[-1]:.4f}")
    print(f"\n  Ultima data de cada serie: {max(s.index.max() for s in historico.values()).date()}")
    print("  Nenhuma linha posterior a data de referencia foi carregada.")

    titulo(3, "MULTISTEP + SVR + DECISAO")
    print("  Treinando e prevendo...\n")
    saida = adaptador.gerar_recomendacao(historico, data_ref)

    print(f"  Modelo: {saida['versao_modelo']}\n")
    print("  Etapa 1, previsao multistep de cada indicador:")
    for indicador, pontos in saida["previsoes"].items():
        valores = ", ".join(f"{p['data']}: {p['valor']:.4f}" for p in pontos)
        print(f"    {indicador:13} {valores}")

    entradas = saida["entradas"]
    final = saida["previsao_final"]
    print("\n  Etapa 2, o SVR consolida as tres previsoes em um fechamento:")
    print(f"    fechamento atual   {entradas['bolsa_atual']:.4f}")
    print(f"    previsto p/ {final['data']}   {final['valor']:.4f}")
    print(f"    variacao prevista  {entradas['variacao_prevista_pct']:+.3f}%")

    print(f"\n  Etapa 3, regra de decisao (limiar de {entradas['limiar_pct']:.1f}%):")
    print(f"    acima de +{entradas['limiar_pct']:.1f}%  -> aplicar")
    print(f"    abaixo de -{entradas['limiar_pct']:.1f}%  -> retirar")
    print("    entre os dois      -> manter")
    print(f"\n    RECOMENDACAO: {saida['recomendacao'].upper()}   (confianca {saida['confianca']})")

    titulo(4, "QUALIDADE DO MODELO (corte de teste do treino do SVR)")
    for chave, valor in entradas["metricas_modelo"].items():
        print(f"  {chave:24} {valor}")
    print("\n  MAE e RMSE estao na unidade do preco; MAPE, em percentual.")
    print("  O ultimo alvo de treino e anterior a primeira origem de teste.")

    titulo(5, "CONTRATO ENTREGUE AO BACKEND")
    print(json.dumps(saida, ensure_ascii=False, indent=2)[:1200])
    print("  ...")
    print("\n  O backend valida esse dicionario e grava em execucoes/previsoes.")
    print("  Qualquer campo fora do contrato vira HTTP 502, sem gravar nada.")

    if not a.sem_explicacao:
        titulo(6, "LIMITE CONHECIDO DO MODELO")
        print(LIMITE)
    conn.close()


if __name__ == "__main__":
    main()
