"""
vofc_parser.py – improved text extraction + multi-pass VOFC parsing

Handles PDFs with tabular Category/Vulnerability/OFC layouts (SAFE, IST, CISA docs).

"""


from pathlib import Path
from typing import Any, Dict, List
import re, json, time

from app.services.ollama_client import generate
from app.utils.logger import get_logger
from app.utils.config import OLLAMA_MODEL


logger = get_logger("vofc-parser")


# =============================
# 🔍 1. Robust Text Extraction
# =============================
def read_file_text(path: Path) -> str:
    """Extracts text from PDF, DOCX, or text/HTML with best-effort fallbacks."""
    try:
        if path.suffix.lower() == ".pdf":
            try:
                import fitz  # PyMuPDF
                text = ""
                with fitz.open(path) as doc:
                    for page in doc:
                        text += page.get_text("text")
                if len(text.strip()) > 500:
                    return text
            except Exception as e:
                logger.warning("PyMuPDF failed (%s). Falling back to pdfminer.", e)


            # pdfminer fallback
            try:
                from pdfminer.high_level import extract_text
                return extract_text(str(path))
            except Exception as e:
                logger.error("pdfminer extraction failed: %s", e)
                return ""
        elif path.suffix.lower() in {".docx"}:
            import docx
            doc = docx.Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
        elif path.suffix.lower() in {".html", ".htm"}:
            return Path(path).read_text(errors="ignore")
        elif path.suffix.lower() in {".txt", ".md"}:
            return Path(path).read_text(errors="ignore")
        else:
            # binary fallback
            return path.read_bytes()[:500000].decode("utf-8", errors="ignore")
    except Exception as e:
        logger.error("read_file_text failed: %s", e)
        return ""


# =======================================
# 🧠 2. Enhanced Model Prompt Definition
# =======================================
PROMPT_TEMPLATE = """You are VOFC Engine, an analytical parser for DHS/CISA SAFE libraries.



You are given a text excerpt from a facility security guide or VOFC library. 

The format may include tables or lines such as:



Category | Vulnerability | Options for Consideration



You must extract all rows into a **single JSON object** using this schema:

{

  "metadata": { "model": "%(model)s" },

  "vulnerabilities": [

     { "id": "auto", "category": "...", "vulnerability": "...", "citations": [] }

  ],

  "options_for_consideration": [

     { "id": "auto", "category": "...", "ofc": "...", "citations": [] }

  ],

  "links": [

     { "vulnerability_id": "auto-ref", "ofc_id": "auto-ref", "strength": "strong", "rationale": "derived from same category or logical pair" }

  ]

}



If the text uses tabular SAFE formatting:

- Treat each Category row as the parent context.

- Each row may have multiple OFCs separated by bullets or line breaks.

- Do **not** hallucinate; only extract what is visible.

- Maintain consistent JSON (no trailing commas, no Markdown).

- Return *only JSON*, no extra commentary.



Text snippet:

\"\"\"%(doc_text)s\"\"\"

"""


# =======================================
# ⚙️ 3. Chunked Multi-Pass Parsing Logic
# =======================================
def chunk_text(text: str, max_len: int = 6000) -> List[str]:
    """Split long text into chunks at paragraph boundaries."""
    parts, buf = [], []
    total_len = 0
    for line in text.splitlines():
        buf.append(line)
        total_len += len(line)
        if total_len > max_len:
            parts.append("\n".join(buf))
            buf, total_len = [], 0
    if buf:
        parts.append("\n".join(buf))
    return parts


def parse_text_to_vofc(doc_text: str) -> Dict[str, Any]:
    """Chunk document, call Ollama, merge structured results."""
    chunks = chunk_text(doc_text)
    results: List[Dict[str, Any]] = []
    logger.info("Parsing document in %d chunk(s)", len(chunks))

    for i, chunk in enumerate(chunks, start=1):
        prompt = PROMPT_TEMPLATE % {"doc_text": chunk, "model": OLLAMA_MODEL}
        try:
            part = generate(prompt, options={"num_predict": 4096})
            if isinstance(part, dict):
                results.append(part)
            else:
                results.append({"raw": part})
            logger.info("Chunk %d/%d parsed.", i, len(chunks))
        except Exception as e:
            logger.error("Chunk %d failed: %s", i, e)
        time.sleep(0.3)  # gentle pacing

    return merge_vofc_results(results)


# =======================================
# 🔗 4. Merge Pass
# =======================================
def merge_vofc_results(parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged = {"vulnerabilities": [], "options_for_consideration": [], "links": []}
    for p in parts:
        if not isinstance(p, dict):
            continue
        for k in merged.keys():
            vals = p.get(k) or []
            if isinstance(vals, list):
                merged[k].extend(vals)
    # Deduplicate by vulnerability/ofc text
    seen_v, seen_o = set(), set()
    dedup_v = []
    for v in merged["vulnerabilities"]:
        vuln_text = v.get("vulnerability") or ""
        if vuln_text and vuln_text not in seen_v:
            seen_v.add(vuln_text)
            dedup_v.append(v)
    merged["vulnerabilities"] = dedup_v
    
    dedup_o = []
    for o in merged["options_for_consideration"]:
        ofc_text = o.get("ofc") or ""
        if ofc_text and ofc_text not in seen_o:
            seen_o.add(ofc_text)
            dedup_o.append(o)
    merged["options_for_consideration"] = dedup_o
    
    logger.info("Merged %d vulnerabilities, %d OFCs",
                len(merged["vulnerabilities"]), len(merged["options_for_consideration"]))
    return merged
