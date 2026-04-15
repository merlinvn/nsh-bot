"""Shared LLM agent runner for conversation worker and playground.

Encapsulates the core loop: LLM call → execute tools → feed results → repeat.
Both ConversationProcessor and playground use this same runner.
"""
from __future__ import annotations

import inspect
import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional

from app.workers.conversation.types import LLMResponse, ToolCallResult

if TYPE_CHECKING:
    from app.workers.conversation.llm import BaseLLM
    from app.mcp.backend import MCPToolBackend


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ToolCallRecord:
    """A tool call that was executed during the agent loop."""
    id: str
    name: str
    input: dict
    output: dict
    success: bool
    latency_ms: int


@dataclass
class AgentRunResult:
    """Final result from an agent run."""
    text: str
    tool_calls: list[ToolCallRecord]
    token_usage: Optional[dict]
    latency_ms: int


# ---------------------------------------------------------------------------
# AgentRunner
# ---------------------------------------------------------------------------


class AgentRunner:
    """Reusable LLM+tools agent loop.

    Used by ConversationProcessor (with DB-backed save_tool_call) and
    playground (without persistence).
    """

    def __init__(
        self,
        llm: "BaseLLM",
        tool_executor: "MCPToolBackend",
        system_prompt: str,
        tool_definitions: list[dict[str, Any]],
        max_steps: int = 3,
        max_tool_calls_per_step: int = 2,
    ) -> None:
        self._llm = llm
        self._tool_executor = tool_executor
        self._system_prompt = system_prompt
        self._tool_definitions = tool_definitions
        self._max_steps = max_steps
        self._max_tool_calls_per_step = max_tool_calls_per_step

    async def run(
        self,
        conversation_history: list[dict[str, Any]],
        new_message: str,
        on_tool_call: Callable[[str, dict, dict, bool, int], Any] | None = None,
    ) -> AgentRunResult:
        """Run the agent loop until no more tool calls or max_steps reached.

        Args:
            conversation_history: prior messages [{role, content}, ...]
            new_message: the new user message to process
        """
        messages = conversation_history + [{"role": "user", "content": new_message}]
        all_tool_calls: list[ToolCallRecord] = []
        total_latency_ms = 0

        for step in range(self._max_steps):
            step_start = time.time()

            response = await self._llm.complete(
                system_prompt=self._system_prompt,
                messages=messages,
                tools=self._tool_definitions,
            )

            total_latency_ms += response.latency_ms or 0

            # Build assistant message content (text + tool_use blocks)
            assistant_content: list[dict] = []
            if response.text:
                assistant_content.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                })

            if assistant_content:
                messages.append({"role": "assistant", "content": assistant_content})

            if not response.tool_calls:
                # No more tool calls — return final text response
                return AgentRunResult(
                    text=response.text or "",
                    tool_calls=all_tool_calls,
                    token_usage=response.token_usage,
                    latency_ms=total_latency_ms,
                )

            # Execute tool calls (up to max per step)
            for tc in response.tool_calls[:self._max_tool_calls_per_step]:
                tool_start = time.time()
                try:
                    result = await self._tool_executor.execute(tc.name, tc.input)
                    tool_latency_ms = int((time.time() - tool_start) * 1000)

                    record = ToolCallRecord(
                        id=tc.id,
                        name=tc.name,
                        input=tc.input,
                        output=result.output,
                        success=True,
                        latency_ms=tool_latency_ms,
                    )

                    if on_tool_call:
                        cb = on_tool_call(tc.name, tc.input, result.output, True, tool_latency_ms)
                        if inspect.iscoroutine(cb):
                            await cb

                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tc.id,
                            "content": json.dumps(result.output, ensure_ascii=False),
                        }],
                    })

                except Exception as exc:
                    tool_latency_ms = int((time.time() - tool_start) * 1000)

                    record = ToolCallRecord(
                        id=tc.id,
                        name=tc.name,
                        input=tc.input,
                        output={"error": str(exc)},
                        success=False,
                        latency_ms=tool_latency_ms,
                    )

                    if on_tool_call:
                        cb = on_tool_call(tc.name, tc.input, {"error": str(exc)}, False, tool_latency_ms)
                        if inspect.iscoroutine(cb):
                            await cb

                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tc.id,
                            "content": json.dumps({"error": str(exc)}, ensure_ascii=False),
                        }],
                    })

                all_tool_calls.append(record)

        # Max steps reached — return what we have
        return AgentRunResult(
            text=response.text or "",
            tool_calls=all_tool_calls,
            token_usage=response.token_usage,
            latency_ms=total_latency_ms,
        )
