"""Anthropic Claude API client wrapper."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import anthropic

from app.workers.conversation.types import LLMResponse, ToolCallResult
from app.workers.shared.logging import get_logger

logger = get_logger("conversation-worker.llm")


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict


class AnthropicLLM:
    """Wrapper around the Anthropic Messages API for Claude."""

    def __init__(self, api_key: str, model: str, timeout: int = 15) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        self.timeout = timeout

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call Claude with tools and return text and/or tool calls.

        Args:
            system_prompt: The system prompt (from DB prompt manager)
            messages: Conversation history + current message
            tools: Tool definitions in Anthropic format

        Returns:
            LLMResponse with text, tool_calls, latency_ms, token_usage
        """
        start_time = time.time()

        try:
            response = await asyncio.wait_for(
                self.client.messages.create(
                    model=self.model,
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

            # Extract text content
            text_parts = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)

            text = "\n".join(text_parts)

            # Extract tool_use blocks
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
                model=self.model,
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
                model=self.model,
                timeout=self.timeout,
                latency_ms=latency_ms,
            )
            raise TimeoutError(f"LLM call timed out after {self.timeout}s")

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "llm_error",
                model=self.model,
                error=str(e),
                error_type=type(e).__name__,
                latency_ms=latency_ms,
            )
            raise
