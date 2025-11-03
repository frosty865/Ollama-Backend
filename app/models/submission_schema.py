from pydantic import BaseModel, Field
from typing import Optional, Any


class ProcessResult(BaseModel):
    status: str = Field(..., description="completed|failed")
    message: Optional[str] = None
    output_path: Optional[str] = None
    meta: Optional[dict] = None


class Submission(BaseModel):
    submission_id: Optional[str] = None
    path: Optional[str] = None  # absolute or relative path to file
    title: Optional[str] = None
    source_url: Optional[str] = None
    sector: Optional[str] = None
    subsector: Optional[str] = None
    year: Optional[int] = None
    extra: Optional[dict[str, Any]] = None

