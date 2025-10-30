#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Heuristic VOFC extractor for the Ollama pipeline.
- Segments document text into Category → Vulnerability → OFCs
- Cleans noise and citations
- Semantic de-dupes OFCs using Ollama embeddings (Windows-safe)
- Ranks OFCs vs. vulnerability context
- Inserts into Supabase "submission_*" mirror tables and link tables

ENV:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  OLLAMA_HOST             (default: http://localhost:11434)
  OLLAMA_EMBED_MODEL      (default: nomic-embed-text)
  LOG_LEVEL               (INFO|DEBUG; default: INFO)
"""

import os
import re
import json
import uuid
import math
import time
import logging
from typing import List, Dict, Any, Tuple
import requests

# ----------------------- Config -----------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
EMBED_MODEL  = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
LOG_LEVEL    = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(levelname)s %(message)s")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# -------------------- Discipline map ------------------
DISCIPLINE_KEYWORDS = {
    "Security Management": ["policy", "plan", "post orders", "awareness", "security manager", "mass notification"],
    "Physical Security":   ["perimeter", "fence", "bollard", "gate", "cpted", "lighting", "illumination", "barrier"],
    "Entry Controls":      ["access control", "badge", "visitor", "screening", "magnetometer", "x-ray"],
    "VSS":                 ["cctv", "camera", "video", "vss", "surveillance"],
    "Security Force":      ["guard", "security force", "roving", "static post", "post orders"],
    "Information Sharing": ["infragard", "fusion", "hsin", "isac", "jttf", "liaison"],
    "Resilience":          ["business continuity", "emergency action", "continuity", "backup", "recovery"],
    "Training":            ["train", "exercise", "drill", "cpr", "stop the bleed", "active shooter"],
}
DEFAULT_DISCIPLINE = "Physical Security"

# -------------------- Helpers -------------------------
def _uuid() -> str:
    return str(uuid.uuid4())

def _cos_sim(a: List[float], b: List[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    return 0.0 if (da == 0 or db == 0) else num / (da * db)

# -------------------- Embeddings ----------------------
def _ollama_embed(texts: List[str]) -> List[List[float]]:
    """Request embeddings from Ollama; Windows-safe fallback included."""
    if not texts:
        return []
    url = f"{OLLAMA_HOST}/api/embeddings"
    payload = {"model": EMBED_MODEL, "prompt": texts}  # Windows-safe key

    try:
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()

        if "embeddings" in data:
            vectors = data["embeddings"]
        elif "data" in data:
            vectors = [d.get("embedding", []) for d in data["data"]]
        elif "embedding" in data:
            vectors = [data.get("embedding", [])]
        else:
            vectors = []

        if not vectors or not any(vectors):
            logging.warning("Ollama returned empty embeddings; using fallback.")
            return [[len(t) % 512 / 512.0] * 10 for t in texts]

        return vectors

    except requests.exceptions.RequestException as e:
        logging.warning(f"Ollama embeddings request failed ({e}); using fallback.")
        return [[len(t) % 512 / 512.0] * 10 for t in texts]

# -------------------- Cleaning & extraction -------------------------
def _clean_line(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip(" -•\u2022\t")
    s = re.sub(r"^[\-\*\u2022]\s*", "", s)
    s = re.sub(r"\s([,.;:])", r"\1", s)
    return s.strip()

def _guess_discipline(text: str, category_hint: str = "") -> str:
    t = f"{category_hint} {text}".lower()
    best = (DEFAULT_DISCIPLINE, 0)
    for disc, kws in DISCIPLINE_KEYWORDS.items():
        score = sum(1 for k in kws if k in t)
        if score > best[1]:
            best = (disc, score)
    return best[0]

def _extract_sources_block(text: str) -> List[str]:
    hits = []
    for line in text.splitlines():
        if re.search(r"\bSource\b[:：]", line, re.I) or re.search(r"https?://", line, re.I):
            hits.append(_clean_line(line))
    return list(dict.fromkeys(hits))

# ------------------ Core Extraction -------------------
CATEGORY_SPLIT = re.compile(r"(?:^|\n)\s*Category\s+([^\n]+?)\s+Vulnerability", re.I)
VULN_OFCS_RE   = re.compile(
    r"Vulnerability(.*?)Options\s+for\s+Consideration(.*?)(?=(?:\n\s*Category\s+)|\Z)",
    re.I | re.S
)

def segment_document(doc: str) -> List[Dict[str, Any]]:
    results = []
    for m in VULN_OFCS_RE.finditer(doc):
        pre = doc[:m.start()]
        cat = "General"
        cat_matches = list(CATEGORY_SPLIT.finditer(pre[-2000:]))
        if cat_matches:
            cat = cat_matches[-1].group(1).strip()
        vul = _clean_line(m.group(1))
        ofc_block = m.group(2)
        results.append({"category": cat or "General",
                        "vulnerability": vul,
                        "ofc_block": ofc_block})
    if not results:
        chunks = re.split(r"(?:^|\n)\s*Options\s+for\s+Consideration\s*[:]?\s*\n", doc, flags=re.I)
        if len(chunks) >= 2:
            vul_guess = _clean_line(chunks[0][-600:])
            results.append({"category": "General", "vulnerability": vul_guess, "ofc_block": chunks[1]})
    return results

def extract_ofcs(ofc_block: str) -> List[str]:
    lines = [l for l in ofc_block.splitlines()]
    cand = []
    for l in lines:
        if re.match(r"\s*[\-\*\u2022•]\s+", l) or re.search(
            r"\b(implement|develop|establish|conduct|train|install|test|exercise|coordinate|provide)\b", l, re.I
        ):
            cand.append(_clean_line(l))
    cand = [c for c in cand if not re.match(r"(?i)^source\b[:：]", c)]
    cand = [c for c in cand if len(c.split()) >= 4]
    return cand

def semantic_dedupe(items: List[str], threshold: float = 0.88) -> List[str]:
    if len(items) <= 1:
        return items
    embs = _ollama_embed(items)
    keep = []
    for i, e in enumerate(embs):
        is_dup = False
        for j, kept in enumerate(keep):
            if _cos_sim(e, kept["emb"]) >= threshold:
                is_dup = True
                break
        if not is_dup:
            keep.append({"text": items[i], "emb": e})
    return [k["text"] for k in keep]

def rank_ofcs(ofcs: List[str], vulnerability: str) -> List[Tuple[str, float]]:
    if not ofcs:
        return []
    embs = _ollama_embed([vulnerability] + ofcs)
    v = embs[0]
    ranked = []
    for i, o in enumerate(ofcs, start=1):
        ranked.append((o, _cos_sim(v, embs[i])))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked

# ------------------ Supabase I/O ----------------------
def _sb_post(table: str, rows: List[dict]) -> List[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase credentials missing.")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    local_headers = {**HEADERS, "Prefer": "return=representation"}
    r = requests.post(url, headers=local_headers, data=json.dumps(rows))
    if r.status_code >= 400:
        raise RuntimeError(f"Supabase insert failed {r.status_code}: {r.text}")
    return r.json()

# ----------------- Public Entry Point -----------------
def process_submission(
    submission_id: str,
    document_text: str,
    source_meta: List[Dict[str, str]] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    t0 = time.time()
    source_meta = source_meta or []
    extracted_sources = _extract_sources_block(document_text)
    if not source_meta and extracted_sources:
        source_meta = [{"source_text": s, "source_title": s, "source_url": ""} for s in extracted_sources]

    segments = segment_document(document_text)
    results = {"submission_id": submission_id, "vulnerabilities": [], "ofcs": [], "links": [], "sources": []}

    src_rows = []
    seen_src = set()
    for src in source_meta:
        key = (src.get("source_title","").strip(), src.get("source_url","").strip(), src.get("source_text","").strip())
        if key in seen_src:
            continue
        seen_src.add(key)
        src_rows.append({
            "id": _uuid(),
            "submission_id": submission_id,
            "source_title": src.get("source_title", "")[:512],
            "source_url": src.get("source_url", "")[:1024],
            "source_text": src.get("source_text", "")[:2048],
        })
    if not dry_run and src_rows:
        src_rows = _sb_post("submission_sources", src_rows)
    results["sources"] = src_rows

    source_ids = [r["id"] for r in src_rows]
    vuln_rows, ofc_rows, link_rows, ofc_src_rows = [], [], [], []

    for seg in segments:
        cat = seg["category"]
        vul_raw = seg["vulnerability"]
        ofc_block = seg["ofc_block"]

        if not vul_raw or len(vul_raw.split()) < 4:
            vul_raw = re.sub(r"^[:\-\s]+", "", _clean_line(vul_raw)) or "Unspecified vulnerability."

        disc = _guess_discipline(vul_raw, category_hint=cat)
        ofcs = extract_ofcs(ofc_block)
        ofcs = semantic_dedupe(ofcs, threshold=0.88)
        ranked = rank_ofcs(ofcs, vul_raw)

        vuln_id = _uuid()
        vuln_rows.append({
            "id": vuln_id,
            "submission_id": submission_id,
            "vulnerability_text": vul_raw[:5000],
            "discipline": disc,
            "category": cat[:256],
            "source": source_meta[0]["source_text"][:2048] if source_meta else None
        })

        for text, score in ranked:
            ofc_id = _uuid()
            ofc_rows.append({
                "id": ofc_id,
                "submission_id": submission_id,
                "vulnerability_id": vuln_id,
                "option_text": text[:5000],
                "discipline": _guess_discipline(text, category_hint=cat),
                "source": source_meta[0]["source_text"][:2048] if source_meta else None,
                "confidence": round(float(score), 3)
            })
            link_rows.append({
                "id": _uuid(),
                "submission_id": submission_id,
                "vulnerability_id": vuln_id,
                "ofc_id": ofc_id
            })
            for sid in source_ids:
                ofc_src_rows.append({
                    "id": _uuid(),
                    "submission_id": submission_id,
                    "ofc_id": ofc_id,
                    "source_id": sid
                })

        results["vulnerabilities"].append({"id": vuln_id, "discipline": disc, "category": cat, "text": vul_raw})
        for text, score in ranked:
            results["ofcs"].append({"text": text, "confidence": round(float(score), 3)})

    if not dry_run:
        if vuln_rows:
            _sb_post("submission_vulnerabilities", vuln_rows)
        if ofc_rows:
            _sb_post("submission_options_for_consideration", ofc_rows)
        if link_rows:
            _sb_post("submission_vulnerability_ofc_links", link_rows)
        if ofc_src_rows:
            _sb_post("submission_ofc_sources", ofc_src_rows)

    results["links"] = {
        "vuln_ofc": len(link_rows),
        "ofc_sources": len(ofc_src_rows)
    }
    results["timing_sec"] = round(time.time() - t0, 3)
    return results

# ----------------- CLI Runner -----------------
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Run VOFC heuristic pipeline on a text file.")
    p.add_argument("--submission-id", required=True, help="Submission UUID")
    p.add_argument("--text-file", required=True, help="Path to plaintext")
    p.add_argument("--source-title", default="", help="Optional source title")
    p.add_argument("--source-url", default="", help="Optional source URL")
    p.add_argument("--source-text", default="", help="Optional source text/filename")
    p.add_argument("--dry-run", action="store_true", help="Do not write to DB; print JSON summary")
    args = p.parse_args()

    with open(args.text_file, "r", encoding="utf-8", errors="ignore") as f:
        doc = f.read()

    src = []
    if args.source_title or args.source_url or args.source_text:
        src = [{"source_title": args.source_title, "source_url": args.source_url, "source_text": args.source_text}]
    res = process_submission(args.submission_id, doc, source_meta=src, dry_run=args.dry_run)
    print(json.dumps(res, indent=2))
