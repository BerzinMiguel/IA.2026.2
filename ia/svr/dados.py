"""Lê arquivos Excel gerados pelo tratamento de dados (ia/tratamento.py)."""
import pandas as pd


def ler_serie(caminho, nome):
    df = pd.read_excel(caminho)
    if not {'Data', 'Valor'}.issubset(df.columns):
        raise ValueError(f'{caminho}: esperado Data e Valor')
    df = df[['Data', 'Valor']].rename(columns={'Valor': nome}).copy()
    df['Data'] = pd.to_datetime(df['Data'], errors='coerce').dt.normalize()
    df[nome] = pd.to_numeric(df[nome].astype(str).str.replace(',', '.', regex=False), errors='coerce')
    return df.dropna().sort_values('Data').drop_duplicates('Data', keep='last')


def juntar_series(dolar, bolsa, volatilidade):
    """Junção interna por data: nunca preencher dias ausentes com dados futuros."""
    a = ler_serie(dolar, 'dolar')
    b = ler_serie(bolsa, 'bolsa')
    c = ler_serie(volatilidade, 'volatilidade')
    df = a.merge(b, on='Data', how='inner').merge(c, on='Data', how='inner')
    if df.empty:
        raise ValueError('Não há datas coincidentes entre as três séries.')
    return df.sort_values('Data').reset_index(drop=True)
