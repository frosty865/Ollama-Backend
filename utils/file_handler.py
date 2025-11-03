import os
from typing import List, Optional
import glob


def normalize_path(path: str | None) -> str | None:
    if path is None:
        return None
    return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))


def ensure_dirs():
    for key, default in [
        ("INCOMING_DIR", os.path.join(os.getcwd(), "data", "incoming")),
        ("PROCESSED_DIR", os.path.join(os.getcwd(), "data", "processed")),
        ("ERROR_DIR", os.path.join(os.getcwd(), "data", "errors")),
        ("VECTOR_DIR", os.path.join(os.getcwd(), "data", "vectors")),
        ("LOG_DIR", os.path.join(os.getcwd(), "logs")),
    ]:
        path = os.getenv(key, default)
        os.makedirs(path, exist_ok=True)


def read_last_lines(path: str, n: int) -> List[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        return [line.rstrip("\n") for line in lines[-n:]]


def get_path(file_hash: Optional[str]) -> str:
    incoming_dir = os.getenv("INCOMING_DIR", os.path.join(os.getcwd(), "data", "incoming"))
    if not file_hash:
        raise FileNotFoundError("file_hash not provided")
    # Try common exact matches
    candidates = [
        os.path.join(incoming_dir, file_hash),
        os.path.join(incoming_dir, f"{file_hash}.pdf"),
        os.path.join(incoming_dir, f"{file_hash}.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # Fallback: search by contains
    pattern = os.path.join(incoming_dir, f"*{file_hash}*")
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    raise FileNotFoundError(f"No file found for hash: {file_hash}")


def get_local_path(file_id: str) -> str:
    incoming_dir = os.getenv("INCOMING_DIR", r"C:\Users\frost\AppData\Local\Ollama\data\incoming")
    return os.path.join(incoming_dir, file_id)


