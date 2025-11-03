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
import subprocess
from typing import List, Dict, Any, Tuple
from difflib import SequenceMatcher
import requests

# Semantic similarity imports
try:
    from sentence_transformers import SentenceTransformer, util
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None
    util = None
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning("sentence-transformers not installed. Semantic linking will be disabled. Install with: pip install sentence-transformers")

# PDF extraction imports
try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

# Optional OCR imports (safe even if missing)
try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    pytesseract = None
    convert_from_path = None
    OCR_AVAILABLE = False

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

# -------------------- PDF Text Extraction (Hybrid: PyPDF2 → Poppler → OCR) -------------------------
def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Attempts to extract readable text from a PDF using:
      1. PyPDF2
      2. Poppler (pdftotext)
      3. OCR fallback (pdf2image + pytesseract)
    Returns: extracted text (str)
    Raises: ValueError if nothing could be extracted.
    """
    # --- 1️⃣  Try PyPDF2 ---
    if PdfReader:
        try:
            reader = PdfReader(pdf_path)
            # Check if PDF is encrypted
            if reader.is_encrypted:
                try:
                    # Try to decrypt with empty password (some PDFs are encrypted but allow empty password)
                    reader.decrypt("")
                    logging.info("PDF was encrypted but decrypted with empty password")
                    # Successfully decrypted, extract text
                    text = "\n".join([page.extract_text() or "" for page in reader.pages])
                except Exception as decrypt_error:
                    logging.warning(f"PDF is encrypted and cannot be decrypted: {decrypt_error}. Trying Poppler...")
                    # Don't return, fall through to Poppler which can handle encrypted PDFs better
                    text = ""  # Set empty text to trigger fallback
            else:
                # Not encrypted, extract normally
                text = "\n".join([page.extract_text() or "" for page in reader.pages])
            
            if len(text.strip()) > 50:
                logging.info(f"PyPDF2 extracted {len(text)} characters from {os.path.basename(pdf_path)}")
                return text
            else:
                logging.warning("PyPDF2 returned <50 chars; attempting Poppler...")
        except Exception as e:
            error_msg = str(e)
            if "PyCryptodome" in error_msg or "encrypted" in error_msg.lower():
                logging.warning(f"PyPDF2 failed (encrypted PDF): {e}. Trying Poppler...")
            else:
                logging.warning(f"PyPDF2 failed: {e}")
    
    # --- 2️⃣  Try Poppler (pdftotext) ---
    # Configure poppler path for Windows (default location: C:\tools\poppler\Library\bin)
    poppler_path = os.getenv('POPPLER_PATH', r'C:\tools\poppler\Library\bin')
    pdftotext_exe = os.path.join(poppler_path, 'pdftotext.exe')
    
    if not os.path.exists(pdftotext_exe):
        # Try alternative common locations
        alt_paths = [
            r'C:\poppler\bin',
            r'C:\tools\poppler\bin',
            os.path.join(os.path.expanduser('~'), 'poppler', 'bin')
        ]
        for alt in alt_paths:
            alt_exe = os.path.join(alt, 'pdftotext.exe')
            if os.path.exists(alt_exe):
                pdftotext_exe = alt_exe
                poppler_path = alt
                break
    
    try:
        # Use full path if found, otherwise try system PATH
        cmd = [pdftotext_exe] if os.path.exists(pdftotext_exe) else ["pdftotext"]
        cmd.extend(["-layout", pdf_path, "-"])
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            errors='replace',  # Replace invalid characters instead of failing
            timeout=60
        )
        text = (result.stdout or "").strip()
        if not text and result.stderr:
            # Sometimes pdftotext outputs warnings to stderr
            logging.debug(f"Poppler stderr: {result.stderr[:200]}")
        if len(text) > 50:
            logging.info(f"Poppler extracted {len(text)} characters from {os.path.basename(pdf_path)}")
            return text
        else:
            logging.warning("Poppler returned <50 chars; attempting OCR...")
    except FileNotFoundError:
        logging.warning("pdftotext not found — install Poppler and retry.")
    except Exception as e:
        logging.warning(f"Poppler extraction error: {e}")

    # --- 3️⃣  OCR fallback (requires pytesseract + pdf2image) ---
    if pytesseract and convert_from_path:
        try:
            logging.info(f"Performing OCR fallback for {os.path.basename(pdf_path)} ...")
            
            # Configure poppler path for pdf2image
            poppler_path_for_images = os.getenv('POPPLER_PATH', r'C:\tools\poppler\Library\bin')
            if not os.path.exists(os.path.join(poppler_path_for_images, 'pdftoppm.exe')):
                alt_paths = [
                    r'C:\poppler\bin',
                    r'C:\tools\poppler\bin',
                    os.path.join(os.path.expanduser('~'), 'poppler', 'bin')
                ]
                for alt in alt_paths:
                    if os.path.exists(os.path.join(alt, 'pdftoppm.exe')):
                        poppler_path_for_images = alt
                        break
            
            images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path_for_images)
            ocr_text = ""
            for i, page in enumerate(images, 1):
                page_text = pytesseract.image_to_string(page, lang="eng")
                ocr_text += page_text
                logging.info(f"   OCR page {i}: {len(page_text)} chars")
            if len(ocr_text.strip()) > 50:
                logging.info(f"OCR extracted {len(ocr_text)} characters total.")
                return ocr_text
            else:
                logging.warning("OCR returned little or no text.")
        except Exception as e:
            logging.error(f"OCR failed: {e}")
    else:
        logging.warning("OCR libraries not installed (pytesseract/pdf2image). Skipping OCR fallback.")

    # --- ❌ None worked ---
    raise ValueError("Could not extract text from PDF (got 0 characters)")

# -------------------- Helpers -------------------------
def _uuid() -> str:
    return str(uuid.uuid4())

def _cos_sim(a: List[float], b: List[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    return 0.0 if (da == 0 or db == 0) else num / (da * db)

# -------------------- Unified VOFC Extraction with Ollama ----------------------
def build_vofc_prompt(text: str) -> str:
    """
    Build an instruction prompt for the VOFC Engine Core.
    Forces structured JSON output for vulnerability + OFC extraction.
    Each vulnerability must include:
    - A Question (assessment question format)
    - What (description of the vulnerability)
    - So What (impact/consequence)
    - Sector and Subsector (based on context)
    - Discipline (security domain)
    """
    return f"""
You are the VOFC Engine Core — an AI agent specialized in
critical-infrastructure vulnerability mapping and risk analysis.

TASK:
Analyze the text below and extract all vulnerabilities and their
corresponding Options for Consideration (OFCs).

CRITICAL REQUIREMENTS:
1. Each vulnerability MUST start with a Question in assessment format (e.g., "Are there adequate security measures in place for...?" or "How does the organization address...?")
2. Each vulnerability MUST include:
   - "what": A clear description of the vulnerability in sentence format
   - "so_what": The impact, consequence, or risk if this vulnerability is not addressed
3. Determine appropriate Sector and Subsector based on context (e.g., "Education", "Healthcare", "Energy", "Government Facilities", etc.)
4. Identify the Discipline (Security Management, Physical Security, Entry Controls, VSS, Security Force, Information Sharing, Resilience, Training)
5. OFCs should be actionable mitigation strategies

Return ONLY valid JSON in this schema:

[
  {{
    "question": "Assessment question about the vulnerability (must be a question)",
    "vulnerability": "Brief vulnerability title",
    "what": "Clear description of the vulnerability in sentence format",
    "so_what": "Impact, consequence, or risk if this vulnerability is not addressed",
    "sector": "Primary sector (e.g., Education, Healthcare, Energy, Government Facilities, Transportation, Water)",
    "subsector": "Specific subsector within the sector (e.g., K-12 Schools, Hospitals, Power Generation, Federal Buildings)",
    "discipline": "Security discipline (Security Management, Physical Security, Entry Controls, VSS, Security Force, Information Sharing, Resilience, Training)",
    "category": "Optional category classification",
    "options_for_consideration": [
      {{
        "option": "Specific actionable mitigation strategy",
        "description": "Detailed description of how to implement this mitigation"
      }}
    ]
  }}
]

EXAMPLES:

Good Question: "Are there adequate threat assessment programs in place to identify students who may pose a risk of violence?"
Good What: "Schools lack comprehensive multidisciplinary threat assessment programs to identify, assess, and intervene with students who may pose a risk of harm to themselves or others."
Good So What: "Without proper threat assessment, warning signs of potential violence may go unnoticed, leading to preventable incidents of targeted school violence."
Good Sector/Subsector: "Education" / "K-12 Schools"

TEXT:
{text}
"""

def call_ollama(prompt: str, model: str = "vofc-engine:latest"):
    """
    Calls Ollama model (CLI or Python SDK) and returns parsed JSON list.
    """
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            errors='replace',
            timeout=300
        )
        raw = result.stdout.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        
        # Try to extract JSON from response (model might add extra text)
        # Look for JSON array or object
        json_start = raw.find('[')
        json_obj_start = raw.find('{')
        if json_start != -1 and (json_obj_start == -1 or json_start < json_obj_start):
            raw = raw[json_start:]
        elif json_obj_start != -1:
            raw = raw[json_obj_start:]
        
        # Find the end of JSON structure
        brace_count = 0
        bracket_count = 0
        json_end = len(raw)
        for i, char in enumerate(raw):
            if char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
                if bracket_count == 0 and json_start != -1:
                    json_end = i + 1
                    break
            elif char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and json_obj_start != -1 and json_start == -1:
                    json_end = i + 1
                    break
        
        raw = raw[:json_end].strip()
        
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                parsed = [parsed]
            return parsed
        except json.JSONDecodeError as e:
            logging.warning(f"JSON parse failed: {e}. Raw output preview:")
            logging.warning(raw[:800])
            return []
    except Exception as e:
        logging.error(f"Ollama call failed: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return []

def normalize_text(text: str):
    """Simple normalization for comparison and matching."""
    return " ".join(text.lower().split())

def similarity(a: str, b: str) -> float:
    """Return similarity ratio (0–1) using normalized tokens."""
    if not a or not b:
        return 0.0
    a_norm, b_norm = normalize_text(a), normalize_text(b)
    return SequenceMatcher(None, a_norm, b_norm).ratio()

def is_duplicate(new_item, existing_items, threshold=0.8):
    """Return True if new_item is similar to an existing item."""
    for existing in existing_items:
        ratio = SequenceMatcher(None, new_item.lower(), existing.lower()).ratio()
        if ratio > threshold:
            return True, existing
    return False, None

def merge_vofc_results(results_list):
    """
    Merge multiple VOFC extraction results (from document chunks)
    into a unified structure, deduplicating via fuzzy similarity.
    """
    merged = {
        "vulnerabilities": [],
        "ofcs": [],
        "links": {"vuln_ofc": 0, "ofc_sources": 0},
        "sources": [],
    }

    vuln_map = {}
    seen_ofcs = set()

    for entry in results_list:
        if not entry:
            continue

        # Handle string or simple list returns
        if isinstance(entry, str):
            entry = [{"vulnerability": entry.strip(), "options_for_consideration": []}]
        elif isinstance(entry, list) and all(isinstance(i, str) for i in entry):
            entry = [{"vulnerability": i.strip(), "options_for_consideration": []} for i in entry]

        for item in entry:
            if isinstance(item, str):
                try:
                    item = json.loads(item)
                except Exception:
                    continue
            if not isinstance(item, dict):
                continue

            vuln_title = item.get("vulnerability") or item.get("title")
            question = item.get("question", "")
            what = item.get("what", "")
            so_what = item.get("so_what", "")
            sector = item.get("sector", "")
            subsector = item.get("subsector", "")
            discipline = item.get("discipline", "")
            category = item.get("category", "General")

            if not vuln_title:
                continue

            description_parts = []
            if what:
                description_parts.append(f"WHAT: {what}")
            if so_what:
                description_parts.append(f"SO WHAT: {so_what}")
            full_description = "\n\n".join(description_parts) or item.get("description", "").strip()

            dedup_key = question or vuln_title
            dup, match_title = is_duplicate(dedup_key, list(vuln_map.keys()), threshold=0.8)
            if dup:
                vuln_id = vuln_map[match_title]
            else:
                vuln_id = str(uuid.uuid4())
                vuln_map[dedup_key] = vuln_id
                merged["vulnerabilities"].append({
                    "id": vuln_id,
                    "question": question.strip(),
                    "category": category,
                    "title": vuln_title.strip(),
                    "description": full_description,
                    "what": what.strip(),
                    "so_what": so_what.strip(),
                    "sector": sector.strip(),
                    "subsector": subsector.strip(),
                    "discipline": discipline.strip(),
                    "severity": item.get("severity", "Unspecified")
                })

            ofcs = item.get("options_for_consideration", [])
            if not isinstance(ofcs, list):
                ofcs = []

            for ofc in ofcs:
                if not isinstance(ofc, dict):
                    continue

                option_title = (
                    ofc.get("option") or
                    ofc.get("option_text") or
                    ofc.get("option_title") or
                    ofc.get("title") or
                    ofc.get("text") or
                    str(ofc)
                ).strip()

                if not option_title:
                    continue

                key = normalize_text(option_title)
                if key not in seen_ofcs:
                    ofc_id = str(uuid.uuid4())
                    merged["ofcs"].append({
                        "id": ofc_id,
                        "title": option_title,
                        "description": ofc.get("description", "").strip() or ofc.get("detail", "").strip(),
                        "linked_vulnerability": None
                    })
                    seen_ofcs.add(key)

    merged["links"]["vuln_ofc"] = len(merged["ofcs"])
    merged["links"]["ofc_sources"] = len(merged["sources"])
    return merged

# ====================================================
#  SEMANTIC LINKER + LEARNING MEMORY
# ====================================================

def link_vulns_to_ofcs(merged, memory_file="data/learned_links.jsonl"):
    """
    Link OFCs to vulnerabilities using semantic similarity.
    Reinforces itself by reusing previously learned pairs.
    """
    if not merged["vulnerabilities"] or not merged["ofcs"]:
        return merged

    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        logging.warning("sentence-transformers not available. Skipping semantic linking.")
        return merged

    model = SentenceTransformer("all-MiniLM-L6-v2")
    # Create directory if memory_file has a directory component
    memory_dir = os.path.dirname(memory_file)
    if memory_dir:
        os.makedirs(memory_dir, exist_ok=True)

    # Load prior learning memory
    learned = []
    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                learned = [json.loads(l) for l in f if l.strip()]
        except Exception as e:
            logging.warning(f"Failed to load learned memory: {e}")

    # Build current embeddings
    vuln_texts = [v["description"] or v["title"] for v in merged["vulnerabilities"]]
    ofc_texts = [o["title"] or o["description"] for o in merged["ofcs"]]
    vuln_emb = model.encode(vuln_texts, convert_to_tensor=True)
    ofc_emb = model.encode(ofc_texts, convert_to_tensor=True)

    new_links = []

    for i, v in enumerate(merged["vulnerabilities"]):
        sims = util.cos_sim(vuln_emb[i], ofc_emb)[0]
        for j, score in enumerate(sims):
            sim = float(score)
            if sim > 0.55:
                merged["ofcs"][j]["linked_vulnerability"] = v["id"]
                new_links.append({
                    "vulnerability": v["title"],
                    "ofc": merged["ofcs"][j]["title"],
                    "similarity": sim
                })

    # 🔁 Reinforcement step: boost or add recurring pairs
    if learned:
        learned_map = {(normalize_text(l["vulnerability"]), normalize_text(l["ofc"])): l["similarity"] for l in learned}
        for o in merged["ofcs"]:
            for v in merged["vulnerabilities"]:
                key = (normalize_text(v["title"]), normalize_text(o["title"]))
                if key in learned_map and learned_map[key] > 0.65:
                    o["linked_vulnerability"] = v["id"]
                    new_links.append({
                        "vulnerability": v["title"],
                        "ofc": o["title"],
                        "similarity": learned_map[key],
                        "reinforced": True
                    })

    # Save new learning data
    if new_links:
        with open(memory_file, "a", encoding="utf-8") as f:
            for link in new_links:
                f.write(json.dumps(link) + "\n")

    merged["links"]["vuln_ofc"] = sum(1 for o in merged["ofcs"] if o.get("linked_vulnerability"))
    return merged

# ====================================================
#  MAIN PARSER ENTRYPOINT
# ====================================================

def process_text_with_vofc_engine(full_text: str, chunk_size: int = 6000):
    """
    Splits long text into manageable chunks, calls Ollama for each,
    merges + links outputs with fuzzy + semantic + learned matching.
    """
    chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
    all_results = []

    logging.info(f"Processing {len(chunks)} chunk(s) ({len(full_text)} chars total)")

    for i, chunk in enumerate(chunks, 1):
        logging.info(f"Processing chunk {i}/{len(chunks)} ({len(chunk)} chars)...")
        prompt = build_vofc_prompt(chunk)
        res = call_ollama(prompt)

        if res:
            valid_res = [r for r in res if isinstance(r, dict)]
            if valid_res:
                logging.info(f"Chunk {i}: Extracted {len(valid_res)} entries")
                all_results.append(valid_res)
            else:
                logging.warning(f"Chunk {i}: No valid dict entries")
        else:
            logging.warning(f"Chunk {i}: No data returned")

    merged = merge_vofc_results(all_results)
    merged = link_vulns_to_ofcs(merged)
    logging.info(
        f"Final result: {len(merged['vulnerabilities'])} vulnerabilities, "
        f"{len(merged['ofcs'])} OFCs, {merged['links']['vuln_ofc']} linked pairs"
    )
    return merged

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
    """Extract source references from text - looks for explicit source labels and URLs."""
    hits = []
    for line in text.splitlines():
        if re.search(r"\bSource\b[:：]", line, re.I) or re.search(r"https?://", line, re.I):
            hits.append(_clean_line(line))
    return list(dict.fromkeys(hits))

def _extract_citation_from_text(text: str, first_n_pages: int = 3) -> Dict[str, Any]:
    """
    Extract citation information from document text, focusing on title page and first few pages.
    Looks for: title, author(s), publication date, organization, document number, etc.
    """
    citation_info = {
        "title": None,
        "authors": [],
        "organization": None,
        "publication_date": None,
        "document_number": None,
        "pages": None,
        "url": None,
        "source_text": ""
    }
    
    # Split text into pages (roughly by double newlines or page breaks)
    pages = re.split(r'\n\s*\n\s*\n+', text[:10000])  # First ~10k chars should cover first few pages
    title_page_text = pages[0] if pages else text[:3000]  # First page or first 3000 chars
    
    # Extract title - usually on first page, often centered or in large text
    # Look for patterns like "TITLE" (all caps), or first significant line
    title_matches = re.findall(r'(?:^|\n)\s*([A-Z][A-Za-z\s:\-]{10,200}?)(?:\n|$)', title_page_text, re.MULTILINE)
    if title_matches:
        # Pick the longest match that looks like a title (not all caps unless very short)
        potential_titles = [t.strip() for t in title_matches if len(t.strip()) > 10 and len(t.strip()) < 200]
        if potential_titles:
            citation_info["title"] = potential_titles[0]
    
    # Extract author(s) - look for "Author:", "By:", "Prepared by:", "Written by:"
    author_patterns = [
        r'(?:Author|Authors|By|Prepared\s+by|Written\s+by)[:\s]+([^\n]{5,200})',
        r'^([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+and\s+[A-Z][a-z]+\s+[A-Z][a-z]+)*)',
    ]
    for pattern in author_patterns:
        matches = re.findall(pattern, title_page_text, re.IGNORECASE | re.MULTILINE)
        if matches:
            authors = [m.strip() for m in matches if len(m.strip()) > 5 and len(m.strip()) < 200]
            if authors:
                citation_info["authors"] = authors[:3]  # Max 3 authors
                break
    
    # Extract organization - look for organization names, agencies
    org_patterns = [
        r'(?:Department|Agency|Organization|Institution|Office)[:\s]+([A-Z][A-Za-z\s&\-]{5,100})',
        r'\b(CISA|DHS|FBI|NSA|NIST|CISA|DOD|DOE|HHS|DOT)\b',
        r'([A-Z][A-Za-z\s]+(?:Department|Agency|Administration|Service|Bureau))',
    ]
    for pattern in org_patterns:
        matches = re.findall(pattern, title_page_text, re.IGNORECASE | re.MULTILINE)
        if matches:
            orgs = [m.strip() for m in matches if len(m.strip()) > 5]
            if orgs:
                citation_info["organization"] = orgs[0]
                break
    
    # Extract publication date - look for dates
    date_patterns = [
        r'(?:Date|Published|Issued|Released)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
        r'\b([A-Za-z]+\s+\d{1,2},?\s+\d{4})\b',
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    ]
    for pattern in date_patterns:
        matches = re.findall(pattern, title_page_text, re.IGNORECASE | re.MULTILINE)
        if matches:
            citation_info["publication_date"] = matches[0].strip()
            break
    
    # Extract document number/ID
    doc_num_patterns = [
        r'(?:Document|Report|Publication|Number|ID)[#:\s]+([A-Z0-9\-]{3,50})',
        r'\b([A-Z]{2,10}[-/]\d{2,6}[-/]\d{2,6})\b',  # Format like CISA-2024-001
    ]
    for pattern in doc_num_patterns:
        matches = re.findall(pattern, title_page_text, re.IGNORECASE | re.MULTILINE)
        if matches:
            citation_info["document_number"] = matches[0].strip()
            break
    
    # Extract URLs
    url_matches = re.findall(r'https?://[^\s\)]+', text[:5000])  # First 5000 chars
    if url_matches:
        citation_info["url"] = url_matches[0]
    
    # Build source text from extracted information
    source_parts = []
    if citation_info["title"]:
        source_parts.append(citation_info["title"])
    if citation_info["authors"]:
        source_parts.append(", ".join(citation_info["authors"]))
    if citation_info["organization"]:
        source_parts.append(citation_info["organization"])
    if citation_info["publication_date"]:
        source_parts.append(f"({citation_info['publication_date']})")
    if citation_info["document_number"]:
        source_parts.append(f"[{citation_info['document_number']}]")
    
    citation_info["source_text"] = ". ".join(source_parts) if source_parts else ""
    
    return citation_info

def _extract_pdf_metadata(pdf_path: str) -> Dict[str, Any]:
    """
    Extract metadata from PDF file using PyPDF2/pypdf.
    Returns title, author, creation date, etc. from PDF metadata.
    """
    metadata = {
        "title": None,
        "author": None,
        "subject": None,
        "creation_date": None,
        "modification_date": None,
        "producer": None,
        "creator": None
    }
    
    # Try PyPDF2
    try:
        import PyPDF2
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            if reader.metadata:
                metadata["title"] = reader.metadata.get("/Title", "").strip() or None
                metadata["author"] = reader.metadata.get("/Author", "").strip() or None
                metadata["subject"] = reader.metadata.get("/Subject", "").strip() or None
                metadata["creation_date"] = str(reader.metadata.get("/CreationDate", "")).strip() or None
                metadata["modification_date"] = str(reader.metadata.get("/ModDate", "")).strip() or None
                metadata["producer"] = str(reader.metadata.get("/Producer", "")).strip() or None
                metadata["creator"] = str(reader.metadata.get("/Creator", "")).strip() or None
        return metadata
    except Exception:
        pass
    
    # Try pypdf (newer alternative)
    try:
        import pypdf
        with open(pdf_path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            if reader.metadata:
                metadata["title"] = reader.metadata.get("/Title", "").strip() or None
                metadata["author"] = reader.metadata.get("/Author", "").strip() or None
                metadata["subject"] = reader.metadata.get("/Subject", "").strip() or None
                metadata["creation_date"] = str(reader.metadata.get("/CreationDate", "")).strip() or None
                metadata["modification_date"] = str(reader.metadata.get("/ModDate", "")).strip() or None
                metadata["producer"] = str(reader.metadata.get("/Producer", "")).strip() or None
                metadata["creator"] = str(reader.metadata.get("/Creator", "")).strip() or None
        return metadata
    except Exception:
        pass
    
    return metadata

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
    pdf_path: str = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    t0 = time.time()
    source_meta = source_meta or []
    
    # Step 1: Extract citation from PDF metadata (if PDF path provided)
    pdf_citation = {}
    if pdf_path and os.path.exists(pdf_path):
        try:
            pdf_meta = _extract_pdf_metadata(pdf_path)
            if pdf_meta.get("title"):
                pdf_citation["source_title"] = pdf_meta["title"]
            if pdf_meta.get("author"):
                pdf_citation["source_text"] = pdf_meta["author"]
            if pdf_meta.get("creation_date"):
                pdf_citation["publication_date"] = pdf_meta["creation_date"]
            if pdf_meta.get("subject"):
                pdf_citation["source_text"] = (pdf_citation.get("source_text", "") + " - " + pdf_meta["subject"]).strip()
        except Exception as e:
            logging.warning(f"Failed to extract PDF metadata: {e}")
    
    # Step 2: Extract citation from document text (title page and first few pages)
    text_citation = _extract_citation_from_text(document_text, first_n_pages=3)
    
    # Step 3: Merge PDF metadata with text-based citation (text takes precedence)
    if not source_meta:
        merged_citation = {
            "source_title": text_citation.get("title") or pdf_citation.get("source_title") or "",
            "source_text": text_citation.get("source_text") or pdf_citation.get("source_text") or "",
            "source_url": text_citation.get("url") or pdf_citation.get("url") or ""
        }
        
        # Build comprehensive source text from all available fields
        source_parts = []
        if merged_citation["source_title"]:
            source_parts.append(merged_citation["source_title"])
        if text_citation.get("authors"):
            source_parts.append(f"Authors: {', '.join(text_citation['authors'])}")
        if text_citation.get("organization"):
            source_parts.append(f"Organization: {text_citation['organization']}")
        if text_citation.get("publication_date"):
            source_parts.append(f"Date: {text_citation['publication_date']}")
        if text_citation.get("document_number"):
            source_parts.append(f"Doc #: {text_citation['document_number']}")
        
        if source_parts and not merged_citation["source_text"]:
            merged_citation["source_text"] = " | ".join(source_parts)
        
        # Add merged citation as primary source if it has content
        if merged_citation["source_title"] or merged_citation["source_text"]:
            source_meta.append(merged_citation)
    
    # Step 4: Also extract explicit source blocks from text
    extracted_sources = _extract_sources_block(document_text)
    if extracted_sources:
        for src_text in extracted_sources:
            # Only add if not already in source_meta
            if not any(s.get("source_text") == src_text for s in source_meta):
                source_meta.append({
                    "source_text": src_text,
                    "source_title": src_text[:200],  # Truncate to reasonable length
                    "source_url": ""
                })

    # Use LLM-based extraction with vofc-engine model
    logging.info("Using LLM-based VOFC extraction (vofc-engine model)")
    merged_results = process_text_with_vofc_engine(document_text, chunk_size=6000)
    
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

    # Process LLM-extracted vulnerabilities
    for vuln in merged_results.get("vulnerabilities", []):
        vuln_id = vuln.get("id", _uuid())
        cat = vuln.get("category", "General")
        vul_raw = vuln.get("title", "") or vuln.get("description", "")
        question = vuln.get("question", "")
        what = vuln.get("what", "")
        so_what = vuln.get("so_what", "")
        sector = vuln.get("sector", "")
        subsector = vuln.get("subsector", "")
        disc = vuln.get("discipline", "") or _guess_discipline(vul_raw, category_hint=cat)
        
        # Build comprehensive vulnerability text
        vulnerability_parts = []
        if question:
            vulnerability_parts.append(f"QUESTION: {question}")
        if what:
            vulnerability_parts.append(f"WHAT: {what}")
        if so_what:
            vulnerability_parts.append(f"SO WHAT: {so_what}")
        if not vulnerability_parts:
            vulnerability_parts.append(vul_raw)
        
        full_vulnerability_text = "\n\n".join(vulnerability_parts)

        vuln_rows.append({
            "id": vuln_id,
            "submission_id": submission_id,
            "vulnerability_text": full_vulnerability_text[:5000],
            "question": question[:512] if question else None,
            "what": what[:2000] if what else None,
            "so_what": so_what[:2000] if so_what else None,
            "sector": sector[:256] if sector else None,
            "subsector": subsector[:256] if subsector else None,
            "discipline": disc[:256] if disc else DEFAULT_DISCIPLINE
        })

        results["vulnerabilities"].append({
            "id": vuln_id,
            "question": question,
            "what": what,
            "so_what": so_what,
            "sector": sector,
            "subsector": subsector,
            "discipline": disc,
            "category": cat,
            "text": full_vulnerability_text
        })

    # Process LLM-extracted OFCs
    # First, build a map of vulnerability IDs by their question/title for matching
    vuln_id_map = {}
    for v in merged_results.get("vulnerabilities", []):
        vuln_id_map[v.get("id")] = v
        # Also map by question for better matching
        if v.get("question"):
            vuln_id_map[v.get("question").strip()] = v.get("id")
    
    for ofc in merged_results.get("ofcs", []):
        ofc_id = ofc.get("id", _uuid())
        option_text = ofc.get("title", "") or ofc.get("description", "")
        linked_vuln_id = ofc.get("linked_vulnerability")
        
        # If no linked vulnerability ID, try to match by semantic similarity to vulnerabilities
        if not linked_vuln_id:
            # Try to find the best matching vulnerability by comparing OFC text to vulnerability text
            best_match = None
            best_score = 0.0
            for vuln in merged_results.get("vulnerabilities", []):
                vuln_text = f"{vuln.get('question', '')} {vuln.get('what', '')} {vuln.get('so_what', '')}"
                score = similarity(option_text, vuln_text)
                if score > best_score and score > 0.3:  # Minimum 30% similarity threshold
                    best_score = score
                    best_match = vuln.get("id")
            
            if best_match:
                linked_vuln_id = best_match
                logging.info(f"Linked OFC '{option_text[:50]}...' to vulnerability {linked_vuln_id[:8]}... (similarity: {best_score:.2f})")
            elif vuln_rows:
                # Fallback: link to first vulnerability
                linked_vuln_id = vuln_rows[0]["id"]
                logging.warning(f"OFC '{option_text[:50]}...' has no linked_vulnerability and no semantic match, linking to first vulnerability {linked_vuln_id[:8]}...")
            else:
                # Create a placeholder vulnerability if none exists
                linked_vuln_id = _uuid()
                cat = "General"
                vuln_rows.append({
                    "id": linked_vuln_id,
                    "submission_id": submission_id,
                    "vulnerability_text": "Unspecified vulnerability"[:5000],
                    "discipline": DEFAULT_DISCIPLINE
                })
                logging.warning(f"Created placeholder vulnerability {linked_vuln_id[:8]}... for unlinked OFC '{option_text[:50]}...'")
        else:
            # Verify the linked vulnerability actually exists in our vuln_rows
            # Check if linked_vuln_id exists in merged_results first
            linked_vuln_exists = any(v.get("id") == linked_vuln_id for v in merged_results.get("vulnerabilities", []))
            if not linked_vuln_exists:
                # Try to find by semantic matching
                best_match = None
                best_score = 0.0
                for vuln in merged_results.get("vulnerabilities", []):
                    vuln_text = f"{vuln.get('question', '')} {vuln.get('what', '')} {vuln.get('so_what', '')}"
                    score = similarity(option_text, vuln_text)
                    if score > best_score and score > 0.3:
                        best_score = score
                        best_match = vuln.get("id")
                
                if best_match:
                    linked_vuln_id = best_match
                    logging.info(f"Re-linked OFC '{option_text[:50]}...' to vulnerability {linked_vuln_id[:8]}... (similarity: {best_score:.2f})")
                elif vuln_rows:
                    logging.warning(f"OFC '{option_text[:50]}...' links to vulnerability {linked_vuln_id[:8]}... which doesn't exist, linking to first vulnerability instead")
                    linked_vuln_id = vuln_rows[0]["id"]
                else:
                    # Create placeholder
                    linked_vuln_id = _uuid()
                    vuln_rows.append({
                        "id": linked_vuln_id,
                        "submission_id": submission_id,
                        "vulnerability_text": "Unspecified vulnerability"[:5000],
                        "discipline": DEFAULT_DISCIPLINE
                    })
            
            # Final check: ensure the vulnerability ID exists in vuln_rows (for database insertion)
            vuln_exists_in_db = any(v["id"] == linked_vuln_id for v in vuln_rows)
            if not vuln_exists_in_db:
                # Find corresponding vulnerability from merged_results and ensure it's in vuln_rows
                for vuln in merged_results.get("vulnerabilities", []):
                    if vuln.get("id") == linked_vuln_id:
                        # Add this vulnerability to vuln_rows if not already there
                        question = vuln.get("question", "")
                        what = vuln.get("what", "")
                        so_what = vuln.get("so_what", "")
                        sector = vuln.get("sector", "")
                        subsector = vuln.get("subsector", "")
                        disc = vuln.get("discipline", "") or DEFAULT_DISCIPLINE
                        
                        vulnerability_parts = []
                        if question:
                            vulnerability_parts.append(f"QUESTION: {question}")
                        if what:
                            vulnerability_parts.append(f"WHAT: {what}")
                        if so_what:
                            vulnerability_parts.append(f"SO WHAT: {so_what}")
                        full_vulnerability_text = "\n\n".join(vulnerability_parts) if vulnerability_parts else "Unspecified vulnerability"
                        
                        vuln_rows.append({
                            "id": linked_vuln_id,
                            "submission_id": submission_id,
                            "vulnerability_text": full_vulnerability_text[:5000],
                            "question": question[:512] if question else None,
                            "what": what[:2000] if what else None,
                            "so_what": so_what[:2000] if so_what else None,
                            "sector": sector[:256] if sector else None,
                            "subsector": subsector[:256] if subsector else None,
                            "discipline": disc[:256] if disc else DEFAULT_DISCIPLINE
                        })
                        logging.info(f"Added missing vulnerability {linked_vuln_id[:8]}... to vuln_rows for OFC linking")
                        break
        
        logging.debug(f"Processing OFC: id={ofc_id[:8]}..., text='{option_text[:50]}...', linked_vuln={linked_vuln_id[:8]}...")

        ofc_rows.append({
            "id": ofc_id,
            "submission_id": submission_id,
            "vulnerability_id": linked_vuln_id,
            "option_text": option_text[:5000],
            "discipline": _guess_discipline(option_text),
            "source": source_meta[0]["source_text"][:2048] if source_meta else None,
            "confidence": 1.0  # LLM-extracted items have high confidence
        })
        
        link_rows.append({
            "id": _uuid(),
            "submission_id": submission_id,
            "vulnerability_id": linked_vuln_id,
            "ofc_id": ofc_id
        })
        
        for sid in source_ids:
            ofc_src_rows.append({
                "id": _uuid(),
                "submission_id": submission_id,
                "ofc_id": ofc_id,
                "source_id": sid
            })

        results["ofcs"].append({
            "text": option_text,
            "confidence": 1.0
        })

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
    p.add_argument("--text-file", required=True, help="Path to plaintext or PDF file")
    p.add_argument("--pdf-path", default="", help="Optional original PDF path for metadata extraction")
    p.add_argument("--source-title", default="", help="Optional source title")
    p.add_argument("--source-url", default="", help="Optional source URL")
    p.add_argument("--source-text", default="", help="Optional source text/filename")
    p.add_argument("--dry-run", action="store_true", help="Do not write to DB; print JSON summary")
    args = p.parse_args()

    # Determine original PDF path for citation extraction
    original_pdf_path = args.pdf_path
    if not original_pdf_path:
        # If text-file is a PDF, use it as the PDF path
        file_ext = os.path.splitext(args.text_file)[1].lower()
        if file_ext == '.pdf':
            original_pdf_path = args.text_file

    # Check if input is a PDF file
    file_ext = os.path.splitext(args.text_file)[1].lower()
    if file_ext == '.pdf':
        logging.info(f"Detected PDF file, extracting text...")
        doc = extract_text_from_pdf(args.text_file)
        if not doc.strip():
            logging.error(f"Failed to extract text from PDF: {args.text_file}")
            exit(1)
        logging.info(f"Extracted {len(doc)} characters from PDF")
    else:
        # Read as plaintext
        with open(args.text_file, encoding="utf-8", errors="ignore") as f:
            doc = f.read()

    src = []
    if args.source_title or args.source_url or args.source_text:
        src = [{"source_title": args.source_title, "source_url": args.source_url, "source_text": args.source_text}]
    res = process_submission(
        args.submission_id, 
        doc, 
        source_meta=src if src else None,
        pdf_path=original_pdf_path if original_pdf_path else None,
        dry_run=args.dry_run
    )
    print(json.dumps(res, indent=2))
