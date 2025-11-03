from fastapi import APIRouter
from utils.logger import get_processing_logger


router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("")
def sync_learning():
    logger = get_processing_logger()
    # Placeholder for syncing learning stats and feedback to Supabase
    logger.info("Sync invoked")
    return {"status": "ok", "synced": True}


