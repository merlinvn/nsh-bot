"""Shared types for conversation worker."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ToolCallResult:
    """Represents a tool call returned from the LLM."""
    id: str
    name: str
    input: dict


@dataclass
class LLMResponse:
    """Represents a response from the LLM."""
    text: str
    tool_calls: list[ToolCallResult]
    latency_ms: int
    token_usage: Optional[dict] = None
