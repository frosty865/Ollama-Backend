import os
from supabase import create_client, Client
from typing import List, Dict, Any


_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is not None:
        return _client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Supabase not configured: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    _client = create_client(url, key)
    return _client


def pull_pending(limit: int = 5) -> List[Dict[str, Any]]:
    sb = get_client()
    res = (
        sb.table("submissions")
        .select("*")
        .eq("status", "submitted")
        .limit(limit)
        .execute()
    )
    return res.data or []


def mark_status(submission_id: str, status: str) -> None:
    sb = get_client()
    sb.table("submissions").update({"status": status}).eq("id", submission_id).execute()


def push_extraction(
    submission_id: str,
    model_version: str,
    data: Dict[str, Any],
    confidence: float,
    runtime_ms: int,
) -> None:
    sb = get_client()
    sb.table("extractions").insert(
        {
            "submission_id": submission_id,
            "model_version": model_version,
            "raw_json": data,
            "confidence": confidence,
            "run_time_ms": runtime_ms,
        }
    ).execute()


def query_embeddings(vector: List[float], match_threshold: float = 0.88, match_count: int = 5) -> List[Dict[str, Any]]:
    sb = get_client()
    res = sb.rpc(
        "match_vulnerabilities",
        {
            "query_embedding": vector,
            "match_threshold": match_threshold,
            "match_count": match_count,
        },
    ).execute()
    return res.data or []


def query_similar_vulnerabilities(vector: List[float], threshold: float = 0.88, count: int = 5) -> List[Dict[str, Any]]:
    return query_embeddings(vector, match_threshold=threshold, match_count=count)


def insert_vulnerability(text: str, embedding_vec: List[float], source_doc: str | None = None) -> None:
    sb = get_client()
    sb.table("vulnerability_library").insert(
        {
            "vulnerability": text,
            "embedding": embedding_vec,
            "source_doc": source_doc,
        }
    ).execute()


