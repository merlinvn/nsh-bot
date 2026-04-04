"""Pydantic schemas for health check endpoints."""
from datetime import datetime

from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    """Status of an individual health check."""
    status: str = Field(..., description="'ok' or 'error'")
    latency_ms: float | None = Field(None, description="Check latency in milliseconds")
    error: str | None = Field(None, description="Error message if status is 'error'")


class HealthResponse(BaseModel):
    """Response for health check endpoints."""
    status: str = Field(..., description="Overall system status: 'alive', 'ready', or 'degraded'")
    checks: dict[str, HealthStatus] | None = Field(None, description="Individual component checks")


class HealthCheck(BaseModel):
    """Individual component health check result."""
    component: str
    healthy: bool
    latency_ms: float | None = None
    error: str | None = None
    checked_at: datetime | None = None
