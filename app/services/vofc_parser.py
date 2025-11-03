from pathlib import Path
from typing import Any, Dict
from app.services.ollama_client import generate
from app.utils.logger import get_logger


logger = get_logger("vofc-parser")


PROMPT_TEMPLATE = """You are VOFC Engine. Extract a structured JSON object from the provided document text.

Return strictly JSON with keys:

- metadata: { title, year, source_url?, sector?, subsector? }

- vulnerabilities: [ { id, title, description, categories?, citations? } ]

- options_for_consideration: [ { id, title, description, categories?, citations? } ]

- links: [ { vulnerability_id, ofc_id, strength: "strong|medium|weak", rationale } ]



The input may be a raw text excerpt; do not hallucinate citations.

If uncertain, leave fields empty rather than guessing.



Document snippet:

\"\"\"{doc_text}\"\"\"

"""


def parse_text_to_vofc(doc_text: str) -> Dict[str, Any]:
    prompt = PROMPT_TEMPLATE.format(doc_text=doc_text[:14000])  # keep prompt sane
    result = generate(prompt)
    return result


def read_file_text(path: Path) -> str:
    # Minimal text extraction; PDF real extraction can be swapped in later
    if path.suffix.lower() in {".txt", ".md"}:
        return path.read_text(errors="ignore")
    if path.suffix.lower() in {".html", ".htm"}:
        return path.read_text(errors="ignore")
    # For PDF/DOCX: placeholder naive extraction
    try:
        if path.suffix.lower() == ".pdf":
            import subprocess, tempfile, os
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "out.txt"
                # Try pdftotext if available
                cmd = ["pdftotext", "-layout", str(path), str(out)]
                subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if out.exists():
                    return out.read_text(errors="ignore")
    except Exception as e:
        logger.warning("PDF extraction fallback failed: %s", e)
    return path.read_bytes()[:200000].decode("utf-8", errors="ignore")

