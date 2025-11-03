import os
from typing import List, Dict, Any
import numpy as np
from . import embedding as emb
from . import supabase_client as sbc


def cosine_similarity(a: List[float], b: List[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def filter_unique(vulnerabilities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    threshold = float(os.getenv("SIM_THRESHOLD", "0.88"))
    unique: List[Dict[str, Any]] = []
    for v in vulnerabilities:
        text = v.get("vulnerability") or v.get("text")
        if not text:
            continue
        vector = emb.embed_text(text)
        matches = sbc.query_embeddings(vector, match_threshold=threshold, match_count=5)
        if not matches:
            unique.append({**v, "embedding": vector})
            continue
        best = 0.0
        for m in matches:
            mvec = m.get("embedding") or []
            if not mvec:
                continue
            best = max(best, cosine_similarity(vector, mvec))
        if best < threshold:
            unique.append({**v, "embedding": vector})
    return unique


