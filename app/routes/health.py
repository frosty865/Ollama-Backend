from flask import Blueprint, jsonify
import requests
from app.utils.config import OLLAMA_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from app.services.supabase_client import supabase
from app.utils.logger import get_logger


bp = Blueprint("health", __name__, url_prefix="/api/system")
logger = get_logger("health")


@bp.get("/health")
def health():
    status = {"flask": "ok", "ollama": "down", "supabase": "down"}
    # Ollama
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        status["ollama"] = "ok" if r.status_code == 200 else "down"
    except Exception:
        status["ollama"] = "down"
    # Supabase
    try:
        if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and supabase():
            status["supabase"] = "ok"
        else:
            status["supabase"] = "not_configured"
    except Exception:
        status["supabase"] = "down"
    return jsonify(status), 200

