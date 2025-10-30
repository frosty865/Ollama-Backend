from fastapi import APIRouter
import time
from utils.logger import get_processing_logger
from utils import supabase_client
from utils.ollama_client import run_inference
from utils.file_handler import get_path, get_local_path
from utils.semantics import filter_unique
from utils import embedding
from numpy import dot
from numpy.linalg import norm


router = APIRouter(prefix="/process-pending", tags=["processing"])


@router.post("")
def process_pending():
    logger = get_processing_logger()
    logger.info("Batch processing started")

    pending = supabase_client.pull_pending(limit=5)
    if not pending:
        logger.info("No pending submissions")
        return {"status": "idle", "processed": []}

    processed: list[str] = []
    for sub in pending:
        sid = sub.get("id")
        file_id = sub.get("ollama_file_id")
        file_path = None
        if file_id:
            file_path = get_local_path(file_id)
        else:
            file_hash = sub.get("file_hash")
            if file_hash:
                file_path = get_path(file_hash)
        if not file_path or not os.path.exists(file_path):
            logger.info(f"Skipping submission {sid}: file not found")
            continue

        supabase_client.mark_status(sid, "processing")
        logger.info(f"Processing submission {sid}")
        start = time.time()
        output = run_inference(file_path)
        if isinstance(output, dict) and isinstance(output.get("vulnerabilities"), list):
            output["vulnerabilities"] = filter_unique(output["vulnerabilities"])

        # Optional: deduplicate and persist new vulnerabilities to library
        def cosine_similarity(a, b):
            return float(dot(a, b) / (norm(a) * norm(b))) if (norm(a) * norm(b)) else 0.0

        extracted_texts = []
        if isinstance(output, dict):
            if isinstance(output.get("vulnerabilities"), list):
                extracted_texts = [v.get("vulnerability") or v.get("text") for v in output["vulnerabilities"] if isinstance(v, dict)]
            elif isinstance(output.get("text"), str):
                # simple fallback: split lines
                extracted_texts = [t.strip() for t in output["text"].splitlines() if t.strip()]

        SIM_THRESHOLD = 0.88
        unique_items = []
        for t in extracted_texts:
            vec = embedding.embed_text(t)
            if not vec:
                continue
            matches = supabase_client.query_similar_vulnerabilities(vec, threshold=SIM_THRESHOLD)
            if not matches:
                unique_items.append({"text": t, "embedding": vec})
                continue
            best = max([m.get("similarity", 0.0) for m in matches]) if matches else 0.0
            if best < SIM_THRESHOLD:
                unique_items.append({"text": t, "embedding": vec})
            else:
                logger.info(f"Skipped duplicate (similarity {best:.3f}) -> {t[:60]}…")

        for item in unique_items:
            try:
                supabase_client.insert_vulnerability(item["text"], item["embedding"], source_doc=file_id)
            except Exception as _:
                pass
        elapsed = int((time.time() - start) * 1000)

        supabase_client.push_extraction(
            sid,
            model_version="vofc-engine:latest",
            data=output,
            confidence=output.get("confidence", 1.0),
            runtime_ms=elapsed,
        )
        supabase_client.mark_status(sid, "completed")
        processed.append(sid)

    logger.info("Batch processing completed")
    return {"status": "ok", "processed": processed}


