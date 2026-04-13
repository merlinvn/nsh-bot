"""Pydantic schemas for playground endpoints."""
from pydantic import BaseModel


class CompletionRequest(BaseModel):
    """Request for single completion test."""
    model_provider: str  # "anthropic" or "openai-compat"
    model_name: str
    system_prompt: str
    messages: list[dict]  # [{"role": str, "content": str}]
    temperature: float | None = 0.7
    max_tokens: int | None = 1024


class PlaygroundChatRequest(BaseModel):
    """Request for playground chat (uses same flow as conversation worker)."""
    system_prompt: str
    messages: list[dict]  # [{"role": "user" | "assistant", "content": str}]
    user_message: str  # New message to send
    temperature: float | None = 0.7


class BenchmarkRequest(BaseModel):
    """Request to run a benchmark."""
    name: str
    test_prompts: list[dict]  # [{"name": str, "messages": [...]}]
    models: list[dict]  # [{"provider": str, "name": str}]
    iterations: int
