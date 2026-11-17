"""Sobe a API e o front na mesma porta.

    python run.py          ->  http://localhost:8000      (dashboard)
                               http://localhost:8000/api/health
"""
import os

from backend import create_app
from backend.config import Config

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=os.getenv("DEBUG", "1") == "1")
