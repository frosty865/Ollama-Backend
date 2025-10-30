import time
from datetime import datetime
from app.utils.supabase_client import get_client
from app.utils import logger


def main():
    sb = get_client()

    # Pull all learning events and softmatches
    events = sb.table("learning_events").select("*").execute().data or []
    softmatches = sb.table("vulnerability_softmatches").select("*").execute().data or []

    if not events and not softmatches:
        logger.log("No learning data available")
        return

    grouped = {}
    for e in events:
        mv = e.get("model_version", "vofc-engine:latest")
        grouped.setdefault(mv, {"accepts": 0, "edits": 0, "total": 0})
        grouped[mv]["total"] += 1
        if e["event_type"] == "accept":
            grouped[mv]["accepts"] += 1
        elif e["event_type"] == "edit":
            grouped[mv]["edits"] += 1

    # Aggregate softmatch counts
    for sm in softmatches:
        mv = sm.get("model_version", "vofc-engine:latest")
        grouped.setdefault(mv, {"accepts": 0, "edits": 0, "total": 0})
        grouped[mv]["softmatches"] = grouped[mv].get("softmatches", 0) + 1

    # Write aggregated stats
    for mv, stats in grouped.items():
        total = stats.get("total", 0)
        accept_rate = round(stats.get("accepts", 0) / total, 3) if total else 0
        avg_edits = round(stats.get("edits", 0) / total, 3) if total else 0
        softcount = stats.get("softmatches", 0)
        row = {
            "model_version": mv,
            "accept_rate": accept_rate,
            "avg_edits": avg_edits,
            "total_events": total,
            "softmatch_count": softcount,
            "last_run": datetime.utcnow().isoformat(),
        }
        sb.table("learning_stats").upsert(row, on_conflict="model_version").execute()
        logger.log(f"Updated learning_stats for {mv}: accept={accept_rate}, edits={avg_edits}, soft={softcount}")


if __name__ == "__main__":
    main()


