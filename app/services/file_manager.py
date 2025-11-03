from pathlib import Path
from typing import Iterable, List, Optional
from app.utils.config import INCOMING_DIR, PROCESSED_DIR, ERRORS_DIR
from app.utils.logger import get_logger


logger = get_logger("file-manager")

SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".html", ".htm"}


def list_pending(limit: int = 100) -> List[Path]:
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for p in INCOMING_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            files.append(p)
    return sorted(files)[:limit]


def move_to_processed(src: Path, out_name: Optional[str] = None) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dst = PROCESSED_DIR / (out_name or src.name)
    try:
        src.rename(dst)
    except Exception:
        # cross-device move fallback
        import shutil
        shutil.move(str(src), str(dst))
    return dst


def move_to_errors(src: Path, reason: str) -> Path:
    ERRORS_DIR.mkdir(parents=True, exist_ok=True)
    dst = ERRORS_DIR / src.name
    logger.error("Moving to errors: %s (%s)", src.name, reason)
    try:
        src.rename(dst)
    except Exception:
        import shutil
        shutil.move(str(src), str(dst))
    return dst

