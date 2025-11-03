# VOFC Ollama Backend (Unified Directory Setup)

- Service root: `C:\Users\frost\AppData\Local\Ollama`
- FastAPI entrypoint: `app/main.py`
- API base: `http://localhost:8000`
- Requires `Authorization: Bearer <BACKEND_API_KEY>` on all endpoints

## Endpoints
- POST `/process-one`
- POST `/process-pending`
- POST `/sync`
- GET `/status`
- GET `/logs`

## Environment
Place `.env` in the service root with keys described in `.env.example`.

## Run Locally
```powershell
python -m pip install -r requirements.txt
python .\app\main.py
```

## Windows Service (NSSM)
Use NSSM to install the service pointing to `app/main.py` and set logs in `logs/`.
