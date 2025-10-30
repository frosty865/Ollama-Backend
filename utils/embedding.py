import os, requests
from . import logger


def embed_text(text: str) -> list[float]:
    url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")
    if not text or len(text.strip()) < 5:
        return []
    payload = {"model": model, "input": text}
    try:
        resp = requests.post(f"{url}/api/embeddings", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        emb = data.get("embedding")
        if not emb:
            raise ValueError("No embedding returned")
        return emb
    except Exception as e:  # noqa: BLE001
        logger.log(f"embed_text failed: {e}")
        return []


