"""Tool registry and executors for the conversation worker.

Backward-compatibility shim — all new code should use registry.py directly.

Exports preserved for backward compatibility with existing imports:
- TOOL_WHITELIST: frozenset of the 4 Phase 1 tool names
- TOOL_DEFINITIONS: static list of tool schemas (Phase 1 whitelist only)
- ToolResult: result dataclass
- ToolExecutor: thin wrapper delegating to LocalToolBackend

The actual tool execution infrastructure lives in registry.py:
- ToolSpec, ToolRegistry, ToolBackend, LocalToolBackend
- get_registry(), MAIN_AGENT_TOOLS, QUOTE_AGENT_TOOLS
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

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
# TOOL_DEFINITIONS — static Phase 1 list for backward compatibility
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "lookup_customer",
        "description": (
            "Find customer by phone number or name. Use this when a customer "
            "provides their phone number or name and you need to look up "
            "their account information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Phone number or name to search for",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_order_status",
        "description": (
            "Query the status of an order by order ID. Use this when a "
            "customer asks about their order status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID to look up",
                },
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "create_support_ticket",
        "description": (
            "Open a support ticket for customer issues that cannot be "
            "resolved through the available tools. Use when a customer has "
            "a complaint, refund request, or needs human agent assistance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Brief subject/summary of the issue",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the issue",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Priority level",
                },
            },
            "required": ["subject", "description"],
        },
    },
    {
        "name": "handoff_request",
        "description": (
            "Flag this conversation for immediate human agent handoff. "
            "Use this sparingly — only when the customer explicitly requests "
            "a human, or the issue requires human judgment beyond what "
            "tools can provide."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Reason for the handoff request",
                },
            },
            "required": ["reason"],
        },
    },
]
