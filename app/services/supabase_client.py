from typing import Optional, Any
from app.utils.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from app.utils.logger import get_logger


logger = get_logger("supabase-client")


try:
    from supabase import create_client, Client  # type: ignore
except Exception as e:
    create_client = None
    Client = None
    logger.warning("Supabase SDK not available: %s", e)


_client: Optional["Client"] = None


def supabase() -> Optional["Client"]:
    global _client
    if _client:
        return _client
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY or not create_client:
        logger.info("Supabase not configured; running without mirror.")
        return None
    _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _client


def insert_submission_meta(table: str, row: dict[str, Any]) -> bool:
    sb = supabase()
    if not sb:
        return False
    try:
        sb.table(table).insert(row).execute()
        return True
    except Exception as e:
        logger.error("Supabase insert failed: %s", e)
        return False


def update_submission_meta(table: str, match: dict[str, Any], patch: dict[str, Any]) -> bool:
    sb = supabase()
    if not sb:
        return False
    try:
        q = sb.table(table).update(patch)
        for k, v in match.items():
            q = q.eq(k, v)
        q.execute()
        return True
    except Exception as e:
        logger.error("Supabase update failed: %s", e)
        return False

