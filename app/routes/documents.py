from flask import Blueprint, request, jsonify
from pathlib import Path
from datetime import datetime
from app.services.file_manager import list_pending, move_to_processed, move_to_errors
from app.services.vofc_parser import read_file_text, parse_text_to_vofc
from app.services.supabase_client import insert_submission_meta, update_submission_meta
from app.utils.config import INCOMING_DIR, PROCESSED_DIR
from app.utils.logger import get_logger
from app.models.submission_schema import Submission, ProcessResult
import json, uuid


bp = Blueprint("documents", __name__, url_prefix="/api/documents")
logger = get_logger("documents")


@bp.post("/submit")
def submit():
    """
    Accepts multipart/form-data (file) or JSON {url?, title?, sector?, ...}.
    For files, writes into /incoming and returns a submission record (local-first).
    """
    if request.content_type and "multipart/form-data" in request.content_type:
        f = request.files.get("file")
        if not f:
            return jsonify({"error": "file is required"}), 400
        fname = f.filename or f"upload-{uuid.uuid4().hex}.bin"
        dest = INCOMING_DIR / fname
        dest.parent.mkdir(parents=True, exist_ok=True)
        f.save(dest)
        sub_id = uuid.uuid4().hex
        insert_submission_meta("submissions", {
            "id": sub_id,
            "title": request.form.get("title"),
            "file_name": fname,
            "source": "tunnel_submission",
            "status": "pending_review",
            "created_at": datetime.utcnow().isoformat() + "Z"
        })
        return jsonify({"submission_id": sub_id, "path": str(dest)}), 200


    data = request.get_json(silent=True) or {}
    # URL mode not implemented in this scaffold
    return jsonify({"message": "URL submissions not implemented in base scaffold"}), 200


def _process_file(path: Path, sub_id: str | None = None) -> ProcessResult:
    """Internal helper to process a single file."""
    sub_id = sub_id or uuid.uuid4().hex
    try:
        text = read_file_text(path)
        vofc = parse_text_to_vofc(text)
        out_name = f"{path.stem}.vofc.json"
        out_path = PROCESSED_DIR / out_name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(vofc, indent=2))

        move_to_processed(path)
        update_submission_meta(
            "submissions",
            {"id": sub_id},
            {
                "status": "completed",
                "output_name": out_name,
                "completed_at": datetime.utcnow().isoformat() + "Z",
            },
        )
        return ProcessResult(status="completed", output_path=str(out_path))
    except Exception as e:
        move_to_errors(path, str(e))
        update_submission_meta(
            "submissions",
            {"id": sub_id},
            {"status": "failed", "error": str(e), "completed_at": datetime.utcnow().isoformat() + "Z"},
        )
        return ProcessResult(status="failed", message=str(e))


@bp.post("/process-one")
def process_one():
    """
    JSON: { path?: string, submission_id?: string }
    If path omitted, process first pending in /incoming.
    """
    body = request.get_json(silent=True) or {}
    path = Path(body.get("path") or "")
    if not path or not path.exists():
        pending = list_pending(limit=1)
        if not pending:
            return jsonify({"message": "no pending files"}), 200
        path = pending[0]

    sub_id = body.get("submission_id")
    result = _process_file(path, sub_id)
    status_code = 200 if result.status == "completed" else 500
    return jsonify(result.model_dump()), status_code


@bp.post("/process-pending")
def process_pending():
    """
    Batch processes up to N pending files from /incoming.
    """
    body = request.get_json(silent=True) or {}
    limit = int(body.get("limit", 10))
    files = list_pending(limit=limit)
    results = []
    for f in files:
        result = _process_file(f)
        results.append(result.model_dump())
    return jsonify({"count": len(results), "results": results}), 200


@bp.post("/sync")
def sync():
    """
    Placeholder for library/submissions sync tasks.
    """
    return jsonify({"message": "sync not implemented in scaffold"}), 200

