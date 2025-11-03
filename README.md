# Ollama-Backend (VOFC Engine)

Production-friendly Flask service that:

- Watches `/incoming` for new docs
- Calls Ollama (`OLLAMA_URL`, `OLLAMA_MODEL`) to extract VOFC JSON
- Writes results to `/processed` (and errors to `/errors`)
- Mirrors metadata to Supabase (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`)
- Exposes health and document-processing APIs used by VOFC Viewer

## Environment (reuses vofc-engine .env)

- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY
- OLLAMA_URL (e.g., http://localhost:11434)
- OLLAMA_MODEL (e.g., vofc-engine)
- STORAGE_ROOT (default: repo root)
- INCOMING_DIR (default: incoming)
- PROCESSED_DIR (default: processed)
- ERRORS_DIR (default: errors)
- LIBRARY_DIR (default: library)
- PORT (default: 8080)
- HOST (default: 0.0.0.0)
- FLASK_ENV (production|development)

## Run

```bash
pip install -r requirements.txt
python -m app.server
```

# or

```bash
gunicorn -w 4 -b 0.0.0.0:${PORT:-8080} app.server:app
```

## Automation

```bash
python ollama_auto_processor.py
```

## API

- GET  `/api/system/health`
- POST `/api/documents/submit`            # multipart/form-data or JSON {url}
- POST `/api/documents/process-one`       # {path? submission_id?}
- POST `/api/documents/process-pending`   # batch local pending
- POST `/api/documents/sync`              # optional future use
