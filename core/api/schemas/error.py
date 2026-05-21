from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class ErrorContext(BaseModel):
    task_id: Optional[str] = None
    user_id: Optional[str] = None
    trace_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    context: ErrorContext = Field(default_factory=ErrorContext)
