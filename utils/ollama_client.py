import os
import httpx
import json


def _base_url() -> str:
    return os.getenv("OLLAMA_URL", "http://localhost:11434")


def get_model_info() -> dict:
    # Minimal placeholder; extend to query GPU metrics if available
    return {"version": "1.0", "gpu_load": None}


def generate_from_document(source_path: str | None, options: dict) -> dict:
    model = os.getenv("OLLAMA_MODEL", "vofc-engine")
    if not model:
        raise RuntimeError("OLLAMA_MODEL not configured")

    payload = {
        "model": model,
        "prompt": f"Process document: {source_path}",
        "options": options or {},
    }
    url = f"{_base_url()}/api/generate"
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


def run_inference(file_path: str) -> dict:
    model = os.getenv("OLLAMA_MODEL", "vofc-engine")
    url = f"{_base_url()}/api/generate"
    prompt = f"Extract vulnerabilities and options for consideration from file: {file_path}"
    payload = {"model": model, "prompt": prompt}

    result_text = ""
    with httpx.Client(timeout=600.0) as client:
        with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    result_text += obj.get("response", "")
                except json.JSONDecodeError:
                    # Non-JSON chunk; skip
                    continue
    return {"text": result_text, "confidence": 1.0}


