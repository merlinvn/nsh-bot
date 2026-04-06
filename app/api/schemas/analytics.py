"""Pydantic schemas for analytics endpoints."""
from pydantic import BaseModel


class AnalyticsOverview(BaseModel):
    """Overview analytics response."""
    period: dict
    total_messages: int
    total_conversations: int
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    fallback_rate: float
