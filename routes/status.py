from fastapi import APIRouter
import os
import time
from utils.ollama_client import get_model_info


router = APIRouter(prefix="/status", tags=["status"])

_started_at = time.time()


@router.get("")
def status():
    uptime_s = int(time.time() - _started_at)
    model = os.getenv("OLLAMA_MODEL", "vofc-engine")
    info = get_model_info()
    return {
        "status": "ok",
        "model": model,
        "uptime": f"{uptime_s}s",
        "gpu_load": info.get("gpu_load"),
        "version": info.get("version"),
    }


