# Security Policy

## Scope
This applies to the VOFC Ollama Backend under `C:\Users\frost\AppData\Local\Ollama` (FastAPI app, scripts, logs, Supabase, Cloudflared, Ollama).

## Secrets and Keys
- Store all secrets in `.env` at the service root; never commit secrets. `.gitignore` excludes it.
- Keys in use:
  - `BACKEND_API_KEY`: protects backend endpoints (required on all except `/status`).
  - `SUPABASE_SERVICE_ROLE_KEY`: server-side DB access; do not expose to clients.
  - `SUPABASE_URL`, `OLLAMA_URL`, `OLLAMA_MODEL`: config (treat as sensitive infra details).
- Principle of least privilege: only the Windows service account should read `.env` and `logs/`.

## Key Generation and Storage
- Generate high-entropy values (≥32 bytes). Prefer OS-generated randomness.
- Store only in `.env` and Vercel/Supabase project settings as needed.
- Never place keys in code, logs, or Git history. Avoid plaintext sharing.

## Rotation Policy
- Rotate `BACKEND_API_KEY` and `SUPABASE_SERVICE_ROLE_KEY` at least quarterly or after any suspected exposure.
- Rotation steps:
  1. Generate new key(s); update `C:\Users\frost\AppData\Local\Ollama\.env`.
  2. Update Vercel env `OLLAMA_API_KEY` to match the backend’s new key.
  3. Restart the service: `nssm restart VOFCBackend`.
  4. Invalidate/remove old keys from all clients; verify new key in use.
- Supabase: rotate service role in the dashboard; ensure only the backend uses it.

## Incident Response
- Indicators: 401/403 spikes, anomalous access, key in logs, or suspected leak.
- Immediate steps:
  1. Revoke/rotate exposed keys (`BACKEND_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`).
  2. Restart backend and verify `/status`.
  3. Review `logs/processing.log`, `logs/system.log`, Cloudflared logs, and Supabase audit logs.
  4. If exposure likely, disable public tunnel temporarily and notify stakeholders.
- After action: document timeline, enable/adjust monitoring, enforce least privilege.

## Data Handling and Logging
- Avoid logging sensitive payloads. Redact tokens if errors must be logged.
- Keep large artifacts (PDFs, DBs, logs) out of Git; they reside locally under `data/` or `automation/`.
- Use embeddings and outputs in compliance with your data governance.

## Reporting Vulnerabilities
- Report privately to the maintainer. Include repro details and redacted logs.
- Do not disclose publicly until a fix is available.

## Hardening Checklist
- `.env` present and not committed.
- `BACKEND_API_KEY` required on all non-health endpoints.
- Windows service runs under a restricted account.
- Firewall rules restrict exposure to the tunnel and localhost.
- Keys rotated regularly; logs reviewed periodically.
