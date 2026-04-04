"""Pydantic schemas for error responses."""
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Structured error detail."""
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Standard error response body."""
    code: str
    message: str
    request_id: str | None = None
