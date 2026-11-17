"""Integração temporal Multistep -> SVR, sem acesso à rede."""
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import mean_absolute_error, mean_squared_error
from Multistep import Multistep
from Bases_para_Treinamento import PreparadorBases
from .modelo import COLUNAS, ModeloSVR, recomendar


def carregar_bases(dolar, bolsa, volatilidade):
    """Lê séries tratadas (ou DataFrames), alinha por interseção sem preencher."""
    series, avisos = [], []
    for nome, origem in zip(COLUNAS, (dolar, bolsa, volatilidade)):
        df = origem.copy() if isinstance(origem, pd.DataFrame) else PreparadorBases._ler_planilha(origem)
        coluna = "Volatilidade_Diaria" if nome == "volatilidade" and "Volatilidade_Diaria" in df else "Valor"
        if not {"Data", coluna}.issubset(df.columns):
            raise ValueError(f"{nome}: esperado Data e {coluna}.")
        df = df[["Data", coluna]].rename(columns={coluna: nome})
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
        if df["Data"].isna().any() or df["Data"].dt.tz is not None:
            raise ValueError(f"{nome}: datas inválidas ou com fuso horário.")
        df["Data"] = df["Data"].dt.normalize()
        if df["Data"].duplicated().any():
            raise ValueError(f"{nome}: datas duplicadas; forneça uma observação diária.")
        primeira_vazia = len(df) > 0 and pd.isna(df.sort_values("Data").iloc[0][nome])
        df[nome] = pd.to_numeric(df[nome].astype(str).str.replace(",", ".", regex=False), errors="coerce")
        # O gerador do grupo deixa apenas a primeira volatilidade vazia.
        df = df.sort_values("Data").reset_index(drop=True)
        if nome == "volatilidade" and primeira_vazia:
            df = df.iloc[1:]
            avisos.append("Primeira volatilidade vazia removida (sem fechamento anterior).")
        if not np.isfinite(df[nome].to_numpy(dtype=float)).all():
            raise ValueError(f"{nome}: valores ausentes, inválidos ou infinitos.")
        if (df[nome] < 0).any() or (nome != "volatilidade" and (df[nome] == 0).any()):
            raise ValueError(f"{nome}: preços devem ser positivos; volatilidade pode ser zero.")
        series.append(df)
    dados = series[0].merge(series[1], on="Data").merge(series[2], on="Data")
    if dados.empty:
        raise ValueError("Não há datas comuns às três séries.")
    if any(len(df) != len(dados) for df in series):
        avisos.append("Usadas somente datas comuns; sem preenchimento. Horizonte conta observações comuns.")
    return dados.sort_values("Data").reset_index(drop=True), avisos


class PipelineIntegrado:
    def __init__(self, dimensao=12, horizonte=2, minimo_treino=60, fracao_teste=0.2, limiar=0.02):
        for nome, valor in (("dimensao", dimensao), ("horizonte", horizonte), ("minimo_treino", minimo_treino)):
            if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
                raise ValueError(f"{nome} deve ser inteiro positivo.")
        if minimo_treino < dimensao + horizonte:
            raise ValueError("minimo_treino deve ser >= dimensao + horizonte.")
        if not 0 < fracao_teste < 1 or not np.isfinite(limiar) or limiar < 0:
            raise ValueError("Fração de teste ou limiar inválido.")
        self.dimensao, self.horizonte = dimensao, horizonte
        self.minimo_treino, self.fracao_teste, self.limiar = minimo_treino, fracao_teste, limiar
        self.modelos = {}

    def _prever_multistep(self, historico):
        return np.column_stack([Multistep.prever_serie(
            historico[col].to_numpy(), historico[col].to_numpy(),
            self.dimensao, self.horizonte) for col in COLUNAS])

    def gerar_historico(self, dados):
        """Janela expansiva: cada origem usa só linhas <= origem, inclusive escala."""
        linhas = []
        for origem in range(self.minimo_treino - 1, len(dados) - self.horizonte):
            previsoes = self._prever_multistep(dados.iloc[:origem + 1])
            for h in range(1, self.horizonte + 1):
                linhas.append({"origem": dados.iloc[origem]["Data"],
                               "data_alvo": dados.iloc[origem + h]["Data"], "horizonte": h,
                               **dict(zip(COLUNAS, previsoes[h - 1])),
                               "alvo": float(dados.iloc[origem + h]["bolsa"])})
        if not linhas:
            raise ValueError("Dados insuficientes para gerar previsões fora da amostra.")
        return pd.DataFrame(linhas)

    def treinar(self, dolar, bolsa, volatilidade, pasta_saida=None):
        dados, avisos = carregar_bases(dolar, bolsa, volatilidade)
        historico = self.gerar_historico(dados)
        origens = historico["origem"].drop_duplicates().sort_values().tolist()
        corte = int(len(origens) * (1 - self.fracao_teste))
        if corte < 1 or corte >= len(origens):
            raise ValueError("Origens insuficientes para separar treino e teste.")
        inicio_teste = origens[corte]
        modelos, metricas, avaliacoes = {}, {}, []
        for h in range(1, self.horizonte + 1):
            base = historico[historico.horizonte == h]
            # Alvos no limite também são excluídos para separação estrita.
            treino = base[(base.origem < inicio_teste) & (base.data_alvo < inicio_teste)]
            teste = base[base.origem >= inicio_teste]
            if len(treino) < 10 or len(teste) < 2:
                raise ValueError(f"Horizonte {h}: exigidos >=10 treinos e >=2 testes após expurgo temporal.")
            modelo = clone(ModeloSVR().pipeline)
            modelo.fit(treino[COLUNAS], treino.alvo)
            previsto = modelo.predict(teste[COLUNAS])
            metricas[str(h)] = {"amostras_treino": len(treino), "amostras_teste": len(teste),
                "MAE": float(mean_absolute_error(teste.alvo, previsto)),
                "RMSE": float(np.sqrt(mean_squared_error(teste.alvo, previsto))),
                "MAPE_pct": float(np.mean(np.abs((teste.alvo.to_numpy() - previsto) / teste.alvo.to_numpy())) * 100),
                "ultimo_alvo_treino": treino.data_alvo.max().date().isoformat(),
                "primeira_origem_teste": inicio_teste.date().isoformat()}
            avaliacao = teste[["origem", "data_alvo", "horizonte", "alvo"]].rename(columns={"alvo": "real"}).copy()
            avaliacao["previsto"] = previsto
            avaliacao["erro"] = avaliacao.real - previsto
            avaliacoes.append(avaliacao)
            modelos[h] = modelo
        self.modelos, self.metricas = modelos, metricas
        self.dados, self.avisos = dados, avisos
        self.avaliacao = pd.concat(avaliacoes, ignore_index=True)
        self.historico = historico
        self.limite_treino = inicio_teste
        if pasta_saida is not None:
            pasta = Path(pasta_saida)
            pasta.mkdir(parents=True, exist_ok=True)
            self.avaliacao.to_csv(pasta / "avaliacao_svr.csv", index=False)
            historico.to_csv(pasta / "previsoes_oos.csv", index=False)
            (pasta / "metricas_svr.json").write_text(json.dumps(metricas, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
            self.salvar(pasta / "pipeline.joblib")
        return metricas

    def prever(self, datas_alvo=None):
        if not self.modelos:
            raise RuntimeError("Treine ou carregue o pipeline antes de prever.")
        origem = self.dados.iloc[-1]
        avisos = list(self.avisos)
        if datas_alvo is None:
            datas = [None] * self.horizonte
            avisos.append("Datas futuras não fornecidas: data_alvo=null; h conta observações comuns, sem presumir feriados.")
        else:
            datas = pd.DatetimeIndex(pd.to_datetime(list(datas_alvo), errors="coerce"))
            if (len(datas) != self.horizonte or datas.hasnans or datas.tz is not None
                or not datas.is_monotonic_increasing or datas.has_duplicates
                or (datas != datas.normalize()).any() or (datas <= origem.Data).any()):
                raise ValueError("Forneça uma data diária futura crescente e única por horizonte.")
            datas = [data.date().isoformat() for data in datas]
        previsoes = self._prever_multistep(self.dados)
        if (previsoes < 0).any():
            avisos.append("MQO retornou indicador negativo; valor preservado, sem truncamento.")
        resultados = []
        for h, valores in enumerate(previsoes, 1):
            previsto = float(self.modelos[h].predict(pd.DataFrame([valores], columns=COLUNAS))[0])
            if not np.isfinite(previsto):
                raise ValueError("SVR produziu previsão não finita.")
            if previsto <= 0:
                avisos.append(f"Horizonte {h}: SVR retornou preço não positivo; previsão acadêmica inválida economicamente.")
            resultados.append({"horizonte": h, "data_alvo": datas[h - 1],
                "indicadores": {col: {"atual": float(origem[col]), "previsto": float(valor)}
                                for col, valor in zip(COLUNAS, valores)},
                "fechamento_previsto": previsto,
                **recomendar(float(origem.bolsa), previsto, self.limiar)})
        return {"data_atualizacao": origem.Data.date().isoformat(),
                **resultados[0], "previsoes": resultados, "avisos": avisos,
                "criterio_horizonte": "observações nas datas comuns às três séries"}

    def salvar(self, caminho):
        if not self.modelos:
            raise RuntimeError("Não há pipeline treinado.")
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"versao": 1, "pipeline": self}, caminho)

    @classmethod
    def carregar(cls, caminho):
        """Somente artefatos confiáveis: joblib pode executar código."""
        artefato = joblib.load(caminho)
        if not isinstance(artefato, dict) or artefato.get("versao") != 1 or not isinstance(artefato.get("pipeline"), cls):
            raise ValueError("Artefato incompatível; use pipeline.joblib da integração.")
        return artefato["pipeline"]
