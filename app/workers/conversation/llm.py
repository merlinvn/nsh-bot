"""LLM client wrappers for Anthropic and OpenAI-compatible endpoints."""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import anthropic
import httpx

from app.workers.conversation.types import LLMResponse, ToolCallResult
from app.workers.shared.logging import get_logger

logger = get_logger("conversation-worker.llm")


class BaseLLM(ABC):
    """Abstract base class for LLM clients."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Return the model name."""
        pass

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call LLM with tools and return text and/or tool calls."""
        pass


class AnthropicLLM(BaseLLM):
    """Wrapper around the Anthropic Messages API for Claude."""

    def __init__(self, api_key: str, model: str, timeout: int = 15) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self.timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call Claude with tools and return text and/or tool calls."""
        start_time = time.time()

        try:
            response = await asyncio.wait_for(
                self.client.messages.create(
                    model=self._model,
                    max_tokens=1024,
                    system=system_prompt,
                    messages=messages,
                    tools=tools if tools else None,
                ),
                timeout=self.timeout,
            )

            latency_ms = int((time.time() - start_time) * 1000)
            token_usage = None

            if response.usage:
                token_usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }

            text_parts = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)

            text = "\n".join(text_parts)

            tool_calls: list[ToolCallResult] = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_calls.append(ToolCallResult(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    ))

            logger.info(
                "llm_response_received",
                provider="anthropic",
                model=self._model,
                latency_ms=latency_ms,
                has_text=bool(text),
                tool_call_count=len(tool_calls),
                input_tokens=token_usage.get("input_tokens") if token_usage else None,
                output_tokens=token_usage.get("output_tokens") if token_usage else None,
            )

            return LLMResponse(
                text=text,
                tool_calls=tool_calls,
                latency_ms=latency_ms,
                token_usage=token_usage,
            )

        except asyncio.TimeoutError:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "llm_timeout",
                provider="anthropic",
                model=self._model,
                timeout=self.timeout,
                latency_ms=latency_ms,
            )
            raise TimeoutError(f"LLM call timed out after {self.timeout}s")

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "llm_error",
                provider="anthropic",
                model=self._model,
                error=str(e),
                error_type=type(e).__name__,
                latency_ms=latency_ms,
            )
            raise


class OpenAICompatLLM(BaseLLM):
    """OpenAI-compatible LLM client for Ollama, LM Studio, LocalAI, etc.

    Supports OpenAI Chat Completions API format with tool calls.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._model = model
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call OpenAI-compatible endpoint with tools."""
        start_time = time.time()

        # Build messages with system prompt
        all_messages = [{"role": "system", "content": system_prompt}]
        all_messages.extend(messages)

        # Build request payload
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": all_messages,
            "max_tokens": 1024,
        }

        # Add tools if provided
        if tools:
            payload["tools"] = tools
            # OpenAI uses tools_output in response
            payload["tool_choice"] = "auto"

        try:
            response = await self._client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract token usage
            token_usage = None
            if "usage" in data:
                token_usage = {
                    "input_tokens": data["usage"].get("prompt_tokens", 0),
                    "output_tokens": data["usage"].get("completion_tokens", 0),
                }

            # Extract text content
            text = ""
            tool_calls: list[ToolCallResult] = []

            for choice in data.get("choices", []):
                message = choice.get("message", {})

                # Text content
                if message.get("content"):
                    text = message["content"]

                # Tool calls (OpenAI format)
                if "tool_calls" in message:
                    for tc in message["tool_calls"]:
                        tool_calls.append(ToolCallResult(
                            id=tc.get("id", ""),
                            name=tc.get("function", {}).get("name", ""),
                            input=tc.get("function", {}).get("arguments", {}),
                        ))

                # Alternative: tool_call result in a later message (for parallel calls)
                if "tool_call" in message:
                    tc = message["tool_call"]
                    tool_calls.append(ToolCallResult(
                        id=tc.get("id", ""),
                        name=tc.get("function", {}).get("name", ""),
                        input=tc.get("function", {}).get("arguments", {}),
                    ))

            logger.info(
                "llm_response_received",
                provider="openai-compat",
                model=self._model,
                latency_ms=latency_ms,
                has_text=bool(text),
                tool_call_count=len(tool_calls),
                input_tokens=token_usage.get("input_tokens") if token_usage else None,
                output_tokens=token_usage.get("output_tokens") if token_usage else None,
            )

            return LLMResponse(
                text=text,
                tool_calls=tool_calls,
                latency_ms=latency_ms,
                token_usage=token_usage,
            )

        except httpx.TimeoutException:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "llm_timeout",
                provider="openai-compat",
                model=self._model,
                timeout=self.timeout,
                latency_ms=latency_ms,
            )
            raise TimeoutError(f"LLM call timed out after {self.timeout}s")

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "llm_error",
                provider="openai-compat",
                model=self._model,
                error=str(e),
                error_type=type(e).__name__,
                latency_ms=latency_ms,
            )
            raise

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


def create_llm_client(
    provider: str,
    anthropic_api_key: str = "",
    anthropic_model: str = "claude-sonnet-4-20250514",
    openai_base_url: str = "http://localhost:11434/v1",
    openai_api_key: str = "ollama",
    openai_model: str = "llama3.2",
    timeout: int = 15,
) -> BaseLLM:
    """Factory function to create LLM client based on provider.

    Args:
        provider: "anthropic" or "openai-compat"
        anthropic_api_key: API key for Anthropic
        anthropic_model: Model name for Anthropic
        openai_base_url: Base URL for OpenAI-compatible API
        openai_api_key: API key for OpenAI-compatible API
        openai_model: Model name for OpenAI-compatible API
        timeout: Request timeout in seconds

    Returns:
        BaseLLM client instance
    """
    if provider == "openai-compat":
        return OpenAICompatLLM(
            base_url=openai_base_url,
            api_key=openai_api_key,
            model=openai_model,
            timeout=timeout,
        )
    else:
        return AnthropicLLM(
            api_key=anthropic_api_key,
            model=anthropic_model,
            timeout=timeout,
        )
