import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(override=False)


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v not in (None, "", "null", "None") else default


REPO_ROOT = Path(__file__).resolve().parents[2]


STORAGE_ROOT = Path(_env("STORAGE_ROOT", str(REPO_ROOT)))
INCOMING_DIR = STORAGE_ROOT / _env("INCOMING_DIR", "incoming")
PROCESSED_DIR = STORAGE_ROOT / _env("PROCESSED_DIR", "processed")
ERRORS_DIR = STORAGE_ROOT / _env("ERRORS_DIR", "errors")
LIBRARY_DIR = STORAGE_ROOT / _env("LIBRARY_DIR", "library")


OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "vofc-engine")


SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = _env("SUPABASE_SERVICE_ROLE_KEY")


HOST = _env("HOST", "0.0.0.0")
PORT = int(_env("PORT", "8080") or "8080")
FLASK_ENV = _env("FLASK_ENV", "production")


def ensure_dirs():
    for p in (INCOMING_DIR, PROCESSED_DIR, ERRORS_DIR, LIBRARY_DIR):
        p.mkdir(parents=True, exist_ok=True)

