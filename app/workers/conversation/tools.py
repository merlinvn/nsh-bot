"""Tool registry and executors for the conversation worker.

Backward-compatibility shim — all new code should use registry.py directly.

Exports preserved for backward compatibility with existing imports:
- TOOL_WHITELIST: frozenset of the 4 Phase 1 tool names
- TOOL_DEFINITIONS: generated from Pydantic models via the registry
- ToolResult: result dataclass
- ToolExecutor: thin wrapper delegating to LocalToolBackend

The actual tool execution infrastructure lives in registry.py:
- ToolSpec, ToolRegistry, ToolBackend, LocalToolBackend
- get_registry(), MAIN_AGENT_TOOLS, QUOTE_AGENT_TOOLS
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.workers.shared.logging import get_logger

logger = get_logger("conversation-worker.tools")

# Import from new registry for internal use
from app.workers.conversation.registry import (
    ToolBackend,
    get_registry,
    LocalToolBackend,
)

# ---------------------------------------------------------------------------
# Backward-compatible exports (unchanged from original)
# ---------------------------------------------------------------------------

TOOL_WHITELIST = frozenset([
    "lookup_customer",
    "get_order_status",
    "create_support_ticket",
    "handoff_request",
    "delegate_to_quote_agent",
    "calculate_shipping_quote",
])


@dataclass
class ToolResult:
    """Result from a tool execution."""
    output: dict
    success: bool


# ---------------------------------------------------------------------------
# ToolExecutor — delegates to LocalToolBackend
# ---------------------------------------------------------------------------

class ToolExecutor:
    """Executes tools with timeout and error handling.

    Backward-compatible wrapper: internally uses LocalToolBackend + ToolRegistry.
    Existing code that calls ToolExecutor() with no arguments continues to work.
    """

    def __init__(self, backend: ToolBackend | None = None) -> None:
        if backend is None:
            registry = get_registry()
            backend = LocalToolBackend(registry)
        self._backend = backend

    async def execute(self, tool_name: str, tool_input: dict) -> ToolResult:
        """Execute a tool by name with input, returning the result.

        Args:
            tool_name: Name of the tool to execute.
            tool_input: Arguments for the tool.

        Returns:
            ToolResult with output dict and success flag.
        """
        if tool_name not in TOOL_WHITELIST:
            logger.warning(
                "unknown_tool_rejected",
                extra={"tool_name": tool_name},
            )
            return ToolResult(
                output={"error": f"Unknown tool: {tool_name}"},
                success=False,
            )

        try:
            result = await self._backend.call(tool_name, tool_input)
            return ToolResult(output=result, success=True)

        except asyncio.TimeoutError:
            logger.error(
                "tool_timeout",
                extra={"tool_name": tool_name},
            )
            return ToolResult(
                output={"error": f"Tool '{tool_name}' timed out"},
                success=False,
            )

        except Exception as e:
            logger.error(
                "tool_exception",
                extra={
                    "tool_name": tool_name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return ToolResult(
                output={"error": str(e)},
                success=False,
            )


# ---------------------------------------------------------------------------
# TOOL_DEFINITIONS — generated from Pydantic models via the registry
# ---------------------------------------------------------------------------

# Generate at import time from the global registry for backward compat.
# This uses the Pydantic input models to produce LLM tool definitions,
# ensuring TOOL_DEFINITIONS always matches what the registry exposes.
_TOOL_DEFINITIONS_CACHE: list[dict] | None = None


def _get_tool_definitions() -> list[dict]:
    """Lazily build and cache TOOL_DEFINITIONS from the global registry."""
    global _TOOL_DEFINITIONS_CACHE
    if _TOOL_DEFINITIONS_CACHE is None:
        registry = get_registry()
        _TOOL_DEFINITIONS_CACHE = registry.definitions(allowed_names=TOOL_WHITELIST)
    return _TOOL_DEFINITIONS_CACHE


class _TOOL_DEFINITIONS_Proxy:
    """Lazy list proxy so len() and iteration work on TOOL_DEFINITIONS."""

    def __iter__(self):
        return iter(_get_tool_definitions())

    def __len__(self) -> int:
        return len(_get_tool_definitions())

    def __getitem__(self, index):
        return _get_tool_definitions()[index]


# Use a proxy object so existing code that iterates or calls len() works
TOOL_DEFINITIONS = _TOOL_DEFINITIONS_Proxy()  # type: ignore[assignment]
