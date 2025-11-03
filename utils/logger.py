import os
import logging
from .file_handler import ensure_dirs


_PROCESSING_LOGGER_NAME = "processing"
_SYSTEM_LOGGER_NAME = "system"


def _configure_logger(name: str, filename: str) -> logging.Logger:
    ensure_dirs()
    log_dir = os.getenv("LOG_DIR", os.path.join(os.getcwd(), "logs"))
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, filename)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    logger.propagate = False
    return logger


def get_processing_logger() -> logging.Logger:
    return _configure_logger(_PROCESSING_LOGGER_NAME, "processing.log")


def get_system_logger() -> logging.Logger:
    return _configure_logger(_SYSTEM_LOGGER_NAME, "system.log")


def log(message: str) -> None:
    logger = get_processing_logger()
    logger.info(message)


