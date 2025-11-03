from fastapi import APIRouter
from utils.file_handler import read_last_lines
import os


router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("")
def get_logs():
    log_dir = os.getenv("LOG_DIR", os.path.join(os.getcwd(), "logs"))
    processing_path = os.path.join(log_dir, "processing.log")
    lines = read_last_lines(processing_path, 200)
    return {"lines": lines}


