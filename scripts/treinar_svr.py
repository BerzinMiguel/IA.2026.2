"""CLI de treino OOS ou inferência do pipeline integrado (Multistep + SVR).

Treinar e salvar o artefato:

    python scripts/treinar_svr.py --dolar dados/Dolar_tratado.xlsx \
        --bolsa dados/Acao_Petrobras_tratado.xlsx \
        --volatilidade resultados/volatilidade.xlsx --saida resultados

Reaproveitar um artefato já treinado (dispensa as bases):

    python scripts/treinar_svr.py --carregar resultados/pipeline.joblib

Para o backend usar esse artefato em vez de treinar a cada execução:

    IA_ARTEFATO=resultados/pipeline.joblib python scripts/atualizar.py
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ia.svr.integracao import PipelineIntegrado  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="Multistep + SVR com avaliação temporal")
    p.add_argument("--dolar")
    p.add_argument("--bolsa")
    p.add_argument("--volatilidade")
    p.add_argument("--carregar", help="pipeline.joblib confiável; dispensa as bases")
    p.add_argument("--saida", default="resultados")
    p.add_argument("--dimensao", type=int, default=12)
    p.add_argument("--horizonte", type=int, default=2)
    p.add_argument("--minimo-treino", type=int, default=60)
    p.add_argument("--datas-alvo", nargs="+")
    a = p.parse_args()
    if a.carregar and any((a.dolar, a.bolsa, a.volatilidade)):
        p.error("Use --carregar ou as três bases, separadamente.")
    if not a.carregar and not all((a.dolar, a.bolsa, a.volatilidade)):
        p.error("Informe --dolar, --bolsa e --volatilidade, ou --carregar.")
    try:
        if a.carregar:
            pipeline = PipelineIntegrado.carregar(a.carregar)
        else:
            pipeline = PipelineIntegrado(a.dimensao, a.horizonte, a.minimo_treino)
            pipeline.treinar(a.dolar, a.bolsa, a.volatilidade, a.saida)
        print(json.dumps({"metricas": pipeline.metricas, "resultado": pipeline.prever(a.datas_alvo)},
                         ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, RuntimeError, OSError, ImportError) as erro:
        p.exit(2, f"Erro: {erro}\n")


if __name__ == "__main__":
    main()
