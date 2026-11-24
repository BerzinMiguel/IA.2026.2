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
    Kernel RBF sobre Min-Max ajustado no treino. C, gamma e epsilon saem de
    uma busca em grade escolhida pelo menor MSE na validacao.
      entrada  dolar e volatilidade previstos para aquele horizonte
      alvo     a VARIACAO do fechamento, bolsa[t+h] / bolsa[t] - 1
    O alvo e variacao, nao nivel de preco. No nivel, a faixa do treino
    (14 a 43 reais) quase nao cruza a do teste (29 a 60) e a busca por menor
    MSE converge para um preditor constante. A previsao volta para reais
    como bolsa[t] * (1 + variacao), e as metricas ficam em reais.
    O treino percorre a serie em janela expansiva: cada origem usa apenas as
    linhas ate ela, inclusive para calcular a escala. A separacao e temporal e
    estrita em treino/validacao/teste: os alvos de cada parte sao anteriores a
    primeira origem da parte seguinte, sem sobreposicao.

  ETAPA 3 - DECISAO
        variacao = (previsto - atual) / atual
        acima de +limiar  -> aplicar
        abaixo de -limiar -> retirar
        entre os dois     -> manter
    A confianca e a distancia relativa ao limiar, saturada em 1,0. Nao e
    probabilidade: so serve para ordenar dias entre si.

  BASELINE, O CRITERIO DE ACEITE
    Junto das metricas vai a persistencia: o preco em t+h e o preco de hoje.
    E o modelo trivial. Um SVR que nao bate esses numeros nao justifica
    existir, por melhor que seja o MSE dele contra si mesmo.

  POR QUE WALK-FORWARD
    Cada execucao recebe do backend apenas o historico ate a data de
    referencia. A previsao do dia 10 e feita com o que existia no dia 10 e
    so depois e comparada ao fechamento real do dia-alvo. Avaliar de outro
    jeito - treinando com a serie toda e medindo no meio dela - produz um
    erro menor e sem significado.
"""

LIMITE = """
  RESOLVIDO - o colapso em preditor constante
    Enquanto o alvo era o nivel do preco, o SVR com kernel RBF nao conseguia
    extrapolar acima da faixa vista no treino. A busca em grade escolhia o
    menor C e o menor gamma possiveis, o modelo virava uma constante (28,08
    para qualquer entrada) e a recomendacao era retirar todo dia, com
    confianca 1,0. Treinar sobre variacao resolveu: o alvo passou a ter a
    mesma faixa no treino e no teste, e o MAE em h=2 caiu de 11,39 para 0,85.

  LIMITE QUE PERMANECE - o ganho sobre a baseline e minimo
    O modelo empata com a persistencia: bate ela por cerca de 1% no MAE em
    h=1 e menos que isso em h=2. Dolar e volatilidade praticamente nao
    carregam informacao sobre a variacao da acao em um ou dois pregoes, o que
    e o esperado para dados diarios. Os parametros escolhidos pela grade
    mudam muito conforme o recorte, sinal de que a busca esta ajustando ruido
    da validacao. O resultado honesto do trabalho e este: a cadeia funciona,
    esta medida de forma correta, e o poder preditivo e baixo.
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
    metricas = entradas["metricas_modelo"]
    baseline = metricas.get("baseline_persistencia") or {}
    for chave, valor in metricas.items():
        if chave != "baseline_persistencia":
            print(f"  {chave:24} {valor}")
    if baseline:
        print()
        print("  COMPARACAO COM A BASELINE (previsto = preco de hoje)")
        print(f"    {'':10} {'MAE':>10} {'RMSE':>10} {'MAPE_pct':>10}")
        for nome, fonte in (("modelo", metricas), ("baseline", baseline)):
            print(f"    {nome:10} {fonte['MAE']:10.4f} {fonte['RMSE']:10.4f} {fonte['MAPE_pct']:10.4f}")
        ganho = 100 * (baseline["MAE"] - metricas["MAE"]) / baseline["MAE"]
        print(f"    ganho do modelo sobre a baseline, em MAE: {ganho:+.2f}%")
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
