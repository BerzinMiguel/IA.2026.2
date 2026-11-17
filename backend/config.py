import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    # Banco local (SQLite) com o histórico de cotações, previsões e recomendações
    DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "dados" / "app.db"))

    # Pasta das planilhas geradas pelo tratamento de dados (ia/tratamento.py)
    DATA_DIR = os.getenv("DATA_DIR", str(BASE_DIR / "dados"))

    # Front servido pelo próprio backend em "/" (mesma origem, sem CORS)
    FRONT_DIR = os.getenv("FRONT_DIR", str(BASE_DIR / "front"))

    # Porta da API; o front usa 8000 quando aberto fora do backend (front/js/api.js)
    PORT = int(os.getenv("PORT", "8000"))

    # "real" = Multistep + SVR do repositório; "mock" = IA simulada (mesmo contrato)
    IA_MODE = os.getenv("IA_MODE", "real")

    # Função do módulo de IA no formato "pacote.modulo:funcao"
    IA_MODULE = os.getenv("IA_MODULE", "ia.adaptador:gerar_recomendacao")

    # Horizonte usado apenas pela IA simulada; no modo real quem manda é IA_HORIZONTE
    HORIZONTE = int(os.getenv("HORIZONTE", "5"))

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
