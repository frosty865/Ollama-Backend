#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOFC Intelligent Extraction Pipeline
Processes documents using multiple Ollama models for better accuracy.
"""

import os
import json
import time
import logging
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
PROCESSED_FOLDER = os.getenv("PROCESSED_FOLDER", "C:/Users/frost/AppData/Local/Ollama/automation/processed")
LIBRARY_FOLDER = os.getenv("LIBRARY_FOLDER", "C:/Users/frost/AppData/Local/Ollama/automation/library")
LOG_DIR = os.getenv("LOG_DIR", "C:/Users/frost/AppData/Local/Ollama/automation/logs")

# Multi-model configuration
MODELS = [
    {"name": "vofc-engine:latest", "weight": 0.6, "role": "primary"},
    {"name": "mistral:latest", "weight": 0.25, "role": "validation"},
    {"name": "llama3:latest", "weight": 0.15, "role": "cross-check"}
]

# Setup logging
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, f"pipeline_{time.strftime('%Y%m%d')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# VOFC Extraction Schema
EXTRACTION_SCHEMA = """
Return STRICT JSON array:
[
  {
    "category": "string",  // e.g., Perimeter Security, Governance / Coordination, VSS, etc.
    "vulnerability": "string",  // problem statement (inverse of requirement/gap)
    "options_for_consideration": [
      {
        "option_text": "string",  // actionable mitigation
        "sources": [
          {"reference_number": 0, "source_text": "string"}  // doc + section/page
        ]
      }
    ]
  }
]
"""

DISCIPLINE_CATEGORIES = [
    'Perimeter Security', 'Access Control', 'Security Management', 
    'Governance / Coordination', 'Communications / Interoperability', 
    'Resilience / Exercises', 'Mechanical / HVAC', 'Building Envelope / Glazing', 
    'Structural / Progressive Collapse', 'Cyber-Physical', 'VSS',
    'Emergency Management', 'Fire Protection', 'Blast Protection',
    'Surveillance Systems', 'Intrusion Detection', 'Command and Control'
]


def extract_text_from_pdf(file_path: Path) -> str:
    """Extract text from PDF file."""
    try:
        import pdfplumber
        
        text = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
        
        return "\n\n".join(text)
    except ImportError:
        logger.error("pdfplumber not installed. Install with: pip install pdfplumber")
        raise
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        raise


def extract_text_from_docx(file_path: Path) -> str:
    """Extract text from DOCX file."""
    try:
        from docx import Document
        
        doc = Document(file_path)
        text = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text.append(paragraph.text)
        
        return "\n\n".join(text)
    except ImportError:
        logger.error("python-docx not installed. Install with: pip install python-docx")
        raise
    except Exception as e:
        logger.error(f"Error extracting text from DOCX: {e}")
        raise


def extract_text(file_path: Path) -> str:
    """Extract text from PDF or DOCX file."""
    suffix = file_path.suffix.lower()
    
    if suffix == '.pdf':
        return extract_text_from_pdf(file_path)
    elif suffix == '.docx':
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def build_extraction_prompt(text: str) -> str:
    """Build the extraction prompt for Ollama."""
    return f"""Extract vulnerabilities and options for consideration from the following document text.

Document text:
{text[:8000]}  # Limit to avoid token limits

{EXTRACTION_SCHEMA}

Categories to use: {', '.join(DISCIPLINE_CATEGORIES[:10])}

Return only valid JSON array, no other text."""


def process_with_model(model_config: dict, prompt: str) -> list:
    """Process text with a single Ollama model."""
    model_name = model_config["name"]
    logger.info(f"🤖 Processing with {model_name} ({model_config['role']})...")
    
    try:
        url = f"{OLLAMA_URL}/api/generate"
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "top_p": 0.9,
                "num_predict": 4096
            }
        }
        
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        
        result = response.json()
        response_text = result.get("response", "")
        
        # Try to extract JSON from response
        import re
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            extracted_json = json.loads(json_match.group())
            if isinstance(extracted_json, list):
                logger.info(f"✅ {model_name} returned {len(extracted_json)} items")
                return extracted_json
        
        logger.warning(f"⚠️ {model_name} returned invalid JSON format")
        return []
    
    except Exception as e:
        logger.error(f"❌ {model_name} failed: {e}")
        return []


def combine_model_results(model_results: list) -> list:
    """Combine and deduplicate results from multiple models."""
    all_results = []
    seen_vulnerabilities = set()
    
    # Primary model results first
    primary_results = [r for r in model_results if r.get("role") == "primary"]
    for result in primary_results:
        for item in result.get("data", []):
            vuln_key = item.get("vulnerability", "").lower().strip()[:100]
            if vuln_key and vuln_key not in seen_vulnerabilities:
                seen_vulnerabilities.add(vuln_key)
                all_results.append(item)
    
    # Then validation and cross-check models
    validation_results = [r for r in model_results if r.get("role") != "primary"]
    for result in validation_results:
        for item in result.get("data", []):
            vuln_key = item.get("vulnerability", "").lower().strip()[:100]
            if vuln_key and vuln_key not in seen_vulnerabilities:
                seen_vulnerabilities.add(vuln_key)
                all_results.append(item)
    
    return all_results


def save_results(results: list, file_path: Path, output_dir: Path):
    """Save processing results to JSON file."""
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = output_dir / f"{file_path.stem}.json"
    
    output_data = {
        "filename": file_path.name,
        "processed_at": datetime.now().isoformat(),
        "models_used": [m["name"] for m in MODELS],
        "vulnerabilities_count": len(results),
        "vulnerabilities": results
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"💾 Saved results to {output_file}")
    return output_file


def update_supabase(file_path: Path, results: list):
    """Update Supabase with processing results."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("⚠️ Supabase credentials not configured, skipping database update")
        return
    
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        
        # Create or update submission record
        submission_data = {
            "type": "ofc",
            "status": "approved" if results else "pending_review",
            "source": "automation",
            "data": json.dumps({
                "document_name": file_path.name,
                "processed_at": datetime.now().isoformat(),
                "models_used": [m["name"] for m in MODELS],
                "vulnerabilities_count": len(results),
                "enhanced_extraction": results
            })
        }
        
        url = f"{SUPABASE_URL}/rest/v1/submissions"
        response = requests.post(url, headers=headers, json=submission_data, params={"select": "id"})
        
        if response.status_code in [200, 201]:
            logger.info(f"✅ Updated Supabase with processing results")
        else:
            logger.warning(f"⚠️ Supabase update returned {response.status_code}: {response.text}")
    
    except Exception as e:
        logger.error(f"❌ Failed to update Supabase: {e}")


def move_to_library(file_path: Path):
    """Move processed file to library folder."""
    try:
        os.makedirs(LIBRARY_FOLDER, exist_ok=True)
        library_path = Path(LIBRARY_FOLDER) / file_path.name
        
        # Handle duplicates
        if library_path.exists():
            timestamp = int(time.time())
            library_path = Path(LIBRARY_FOLDER) / f"{file_path.stem}_{timestamp}{file_path.suffix}"
        
        file_path.rename(library_path)
        logger.info(f"📚 Moved {file_path.name} to library")
        return library_path
    except Exception as e:
        logger.error(f"❌ Failed to move file to library: {e}")
        return None


def process_document(file_path: Path):
    """Main document processing function."""
    start_time = time.time()
    logger.info("=" * 50)
    logger.info(f"🚀 Processing document: {file_path.name}")
    logger.info("=" * 50)
    
    try:
        # 1. Extract text
        logger.info("📄 Extracting text from document...")
        text = extract_text(file_path)
        logger.info(f"✅ Extracted {len(text)} characters from document")
        
        if len(text) < 100:
            raise ValueError("Extracted text too short (may be image-only PDF)")
        
        # 2. Build prompt
        prompt = build_extraction_prompt(text)
        
        # 3. Process with multiple models
        logger.info(f"🔄 Processing with {len(MODELS)} models in parallel...")
        model_results = []
        
        for model_config in MODELS:
            data = process_with_model(model_config, prompt)
            model_results.append({
                "model": model_config["name"],
                "role": model_config["role"],
                "weight": model_config["weight"],
                "data": data
            })
        
        # 4. Combine results
        logger.info("🔗 Combining results from all models...")
        combined_results = combine_model_results(model_results)
        logger.info(f"✅ Combined into {len(combined_results)} unique vulnerabilities")
        
        # 5. Save results
        results_file = save_results(combined_results, file_path, Path(PROCESSED_FOLDER))
        
        # 6. Update Supabase
        update_supabase(file_path, combined_results)
        
        # 7. Move to library
        library_path = move_to_library(file_path)
        
        elapsed = time.time() - start_time
        logger.info("=" * 50)
        logger.info(f"✅ Processing complete in {elapsed:.2f} seconds")
        logger.info(f"📊 Found {len(combined_results)} vulnerabilities")
        logger.info(f"💾 Results saved to: {results_file}")
        logger.info(f"📚 Original file moved to: {library_path}")
        logger.info("=" * 50)
        
        return {
            "success": True,
            "vulnerabilities_count": len(combined_results),
            "results_file": str(results_file),
            "library_path": str(library_path) if library_path else None,
            "processing_time": elapsed
        }
    
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("=" * 50)
        logger.error(f"❌ Processing failed after {elapsed:.2f} seconds")
        logger.error(f"Error: {e}")
        logger.error("=" * 50)
        raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="VOFC Intelligent Extraction Pipeline")
    parser.add_argument("--file", required=True, help="Path to PDF or DOCX file")
    args = parser.parse_args()
    
    file_path = Path(args.file)
    
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return 1
    
    try:
        result = process_document(file_path)
        return 0 if result["success"] else 1
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())

