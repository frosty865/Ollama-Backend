from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

# Ensure environment is loaded from the unified directory
load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"), override=False)

from routes.process_one import router as process_one_router
from routes.process_pending import router as process_pending_router
from routes.sync import router as sync_router
from routes.status import router as status_router
from routes.logs import router as logs_router
from routes.files_upload import router as files_upload_router


def require_api_key(authorization: str | None = Header(default=None)):
    expected_key = os.getenv("BACKEND_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server not configured: BACKEND_API_KEY missing")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")


app = FastAPI(title="VOFC Ollama Backend", version="1.0.0")

# CORS can be tightened as needed; kept permissive for tunnel use
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"service": "vofc-backend", "status": "ok"}


# Protected routes
app.include_router(process_one_router, dependencies=[Depends(require_api_key)])
app.include_router(process_pending_router, dependencies=[Depends(require_api_key)])
app.include_router(sync_router, dependencies=[Depends(require_api_key)])
# Allow unauthenticated health check on /status
app.include_router(status_router)
app.include_router(logs_router, dependencies=[Depends(require_api_key)])
app.include_router(files_upload_router, dependencies=[Depends(require_api_key)])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)


