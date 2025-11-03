from flask import Flask, jsonify
from app.routes.health import bp as health_bp
from app.routes.documents import bp as documents_bp
from app.utils.config import ensure_dirs, HOST, PORT, FLASK_ENV
from app.utils.logger import get_logger


logger = get_logger("server")


def create_app() -> Flask:
    ensure_dirs()
    app = Flask(__name__)
    app.register_blueprint(health_bp)
    app.register_blueprint(documents_bp)


    @app.get("/")
    def root():
        return jsonify({"service": "ollama-backend", "env": FLASK_ENV})


    return app


app = create_app()


if __name__ == "__main__":
    logger.info("Starting Ollama-Backend on %s:%s (%s)", HOST, PORT, FLASK_ENV)
    app.run(host=HOST, port=PORT)

