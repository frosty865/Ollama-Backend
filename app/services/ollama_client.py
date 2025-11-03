import requests, json
from typing import Any, Optional
from app.utils.config import OLLAMA_URL, OLLAMA_MODEL
from app.utils.logger import get_logger


logger = get_logger("ollama-client")


def generate(prompt: str, options: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Calls Ollama /api/generate with a structured prompt.
    Expects model to return a single JSON payload block.
    """
    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if options:
        payload["options"] = options


    logger.debug("Ollama request → %s", url)
    r = requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    # Ollama returns {"response": "..."} — attempt to JSON-decode content
    text = data.get("response", "").strip()
    try:
        return json.loads(text)
    except Exception:
        logger.warning("Model did not return JSON; wrapping as text.")
        return {"raw_text": text}

