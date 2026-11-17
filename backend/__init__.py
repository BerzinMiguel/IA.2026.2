from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from .config import Config
from .db import close_db, connect, init_db


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)

    app.json.ensure_ascii = False  # acentos legíveis no JSON
    CORS(app, origins=app.config["CORS_ORIGINS"])

    conn = connect(app.config["DB_PATH"])
    init_db(conn)
    conn.close()
    app.teardown_appcontext(close_db)

    from .routes.api import bp
    app.register_blueprint(bp)

    # ----- Front-end servido na mesma origem da API (dispensa CORS e Live Server) -----
    def _front(arquivo: str):
        pasta = Path(app.config["FRONT_DIR"])
        if not (pasta / arquivo).is_file():
            return jsonify(erro="recurso não encontrado"), 404
        return send_from_directory(pasta, arquivo)

    @app.get("/")
    def inicio():
        return _front("index.html")

    @app.get("/<path:arquivo>")
    def estaticos(arquivo):
        if arquivo.startswith("api/"):
            return jsonify(erro="recurso não encontrado"), 404
        return _front(arquivo)

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify(erro="recurso não encontrado"), 404

    @app.errorhandler(500)
    def internal(_e):
        return jsonify(erro="erro interno"), 500

    return app
