from fastapi import APIRouter, File, UploadFile, Header, HTTPException
from hashlib import sha256
import os
import time

from utils.logger import get_processing_logger


router = APIRouter(prefix="/files", tags=["files"])

UPLOAD_DIR = os.getenv("INCOMING_DIR", r"C:\Users\frost\AppData\Local\Ollama\data\incoming")
API_KEY = os.getenv("BACKEND_API_KEY")


@router.post("/upload")
async def upload_file(file: UploadFile, authorization: str = Header(None)):
    if authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    start = time.time()

    contents = await file.read()
    file_hash = sha256(contents).hexdigest()
    safe_name = f"{file_hash[:12]}_{file.filename}"
    full_path = os.path.join(UPLOAD_DIR, safe_name)

    with open(full_path, "wb") as f:
        f.write(contents)

    elapsed = int((time.time() - start) * 1000)
    logger = get_processing_logger()
    logger.info(f"Uploaded {file.filename} ({len(contents)} bytes) in {elapsed}ms -> {safe_name}")

    return {
        "status": "ok",
        "ollama_file_id": safe_name,
        "file_hash": file_hash,
        "size_bytes": len(contents),
        "elapsed_ms": elapsed,
    }


