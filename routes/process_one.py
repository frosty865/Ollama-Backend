from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from utils.ollama_client import generate_from_document
from utils.semantics import filter_unique
from utils.file_handler import normalize_path
from utils.logger import get_processing_logger


router = APIRouter(prefix="/process-one", tags=["processing"])


class ProcessOneRequest(BaseModel):
    file_path: Optional[str] = None
    submission_id: Optional[str] = None
    options: Optional[Dict[str, Any]] = None


@router.post("")
def process_one(req: ProcessOneRequest):
    logger = get_processing_logger()
    if not req.file_path and not req.submission_id:
        raise HTTPException(status_code=400, detail="Provide either file_path or submission_id")

    source_path = normalize_path(req.file_path) if req.file_path else None
    # Here we could fetch by submission_id from Supabase to get the source file; placeholder keeps it local.

    try:
        result = generate_from_document(source_path=source_path, options=req.options or {})
        # If structured vulnerabilities are present, filter for uniqueness before returning
        if isinstance(result, dict) and isinstance(result.get("vulnerabilities"), list):
            result["vulnerabilities"] = filter_unique(result["vulnerabilities"])
        logger.info(f"Processed document: {source_path or req.submission_id}")
        return {"status": "ok", "result": result}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Processing failed")
        raise HTTPException(status_code=500, detail=str(exc))


