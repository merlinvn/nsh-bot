"""Tool registry and backend protocol for the conversation worker.

Architecture:
- ToolSpec: dataclass describing a tool (name, schema, handler, timeout, tags)
- ToolBackend: Protocol — interface for calling tools (local or remote/MCP)
- LocalToolBackend: calls handlers directly from the registry
- ToolRegistry: manages tool registration and exposes LLM-compatible definitions
- get_registry(): singleton accessor, bootstraps defaults on first call

This enables:
- Multiple agent tool sets (MAIN_AGENT_TOOLS, QUOTE_AGENT_TOOLS)
- Multi-tenant tool filtering per agent/tenant
- Swap LocalToolBackend for MCPToolBackend without changing executor
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

# Import handlers for bootstrap — avoid circular imports by importing lazily
from app.workers.shared.logging import get_logger

logger = get_logger("conversation-worker.registry")

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ToolHandler = Callable[[dict], Awaitable[dict]]


@dataclass
class ToolSpec:
    """Specification for a single tool.

    Attributes:
        name: Unique tool identifier.
        description: Human-readable description for the LLM.
        input_schema: JSON schema for tool input (Anthropic/OpenAI compatible).
        handler: Async callable that implements the tool logic.
        timeout_seconds: Max execution time before TimeoutError is raised.
        enabled: Whether the tool is active (excluded from definitions when False).
        tags: Arbitrary labels for grouping/filtering (e.g. "customer", "quote").
    """
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    timeout_seconds: float = 5.0
    enabled: bool = True
    tags: tuple[str, ...] = ()


class ToolBackend(Protocol):
    """Protocol for tool execution backends.

    The executor doesn't care whether tools run locally, over HTTP, or via MCP.
    Implement this protocol to add a new backend.
    """

    async def call(self, tool_name: str, tool_input: dict) -> dict:
        """Execute a tool and return its output dict.

        Raises:
            ValueError: if the tool is unknown or disabled.
            asyncio.TimeoutError: if the tool exceeds its timeout.
        """
        ...


# ---------------------------------------------------------------------------
# Local backend
# ---------------------------------------------------------------------------

class LocalToolBackend:
    """Executes tools by calling handlers registered in a ToolRegistry."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def call(self, tool_name: str, tool_input: dict) -> dict:
        """Look up the tool in the registry and run its handler."""
        spec = self._registry.get(tool_name)
        if spec is None:
            raise ValueError(f"Unknown tool: {tool_name}")
        if not spec.enabled:
            raise ValueError(f"Disabled tool: {tool_name}")
        return await asyncio.wait_for(
            spec.handler(tool_input),
            timeout=spec.timeout_seconds,
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Central registry for all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        """Register a tool. Raises KeyError if name is already registered."""
        if spec.name in self._tools:
            raise KeyError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        """Look up a tool spec by name. Returns None if not found."""
        return self._tools.get(name)

    def definitions(
        self,
        allowed_names: set[str] | None = None,
        include_disabled: bool = False,
    ) -> list[dict]:
        """Return tool definitions in Anthropic/OpenAI schema format.

        Args:
            allowed_names: If provided, only include tools in this set.
            include_disabled: If False (default), exclude tools with enabled=False.
        """
        result = []
        for spec in self._tools.values():
            if allowed_names is not None and spec.name not in allowed_names:
                continue
            if not include_disabled and not spec.enabled:
                continue
            result.append({
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
            })
        return result


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Get or create the global ToolRegistry singleton.

    Bootstraps with all Phase 1 tool specs on first call.
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _bootstrap_defaults(_registry)
    return _registry


# ---------------------------------------------------------------------------
# Bootstrap — registers all Phase 1 tools
# ---------------------------------------------------------------------------

def _bootstrap_defaults(registry: ToolRegistry) -> None:
    """Register all Phase 1 tools with the registry."""
    # Import here to avoid circular import at module level
    from app.workers.conversation import handlers

    specs = [
        ToolSpec(
            name="lookup_customer",
            description=(
                "Find customer by phone number or name. Use this when a customer "
                "provides their phone number or name and you need to look up "
                "their account information."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Phone number or name to search for",
                    },
                },
                "required": ["query"],
            },
            handler=handlers.lookup_customer,
            timeout_seconds=5.0,
            enabled=True,
            tags=("customer",),
        ),
        ToolSpec(
            name="get_order_status",
            description=(
                "Query the status of an order by order ID. Use this when a "
                "customer asks about their order status."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The order ID to look up",
                    },
                },
                "required": ["order_id"],
            },
            handler=handlers.get_order_status,
            timeout_seconds=5.0,
            enabled=True,
            tags=("order",),
        ),
        ToolSpec(
            name="create_support_ticket",
            description=(
                "Open a support ticket for customer issues that cannot be "
                "resolved through the available tools. Use when a customer has "
                "a complaint, refund request, or needs human agent assistance."
            ),
            input_schema={
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
            handler=handlers.create_support_ticket,
            timeout_seconds=5.0,
            enabled=True,
            tags=("support",),
        ),
        ToolSpec(
            name="handoff_request",
            description=(
                "Flag this conversation for immediate human agent handoff. "
                "Use this sparingly — only when the customer explicitly requests "
                "a human, or the issue requires human judgment beyond what "
                "tools can provide."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Reason for the handoff request",
                    },
                },
                "required": ["reason"],
            },
            handler=handlers.handoff_request,
            timeout_seconds=3.0,
            enabled=True,
            tags=("handoff",),
        ),
        ToolSpec(
            name="delegate_to_quote_agent",
            description=(
                "Delegate to the quote subagent to calculate shipping rates. "
                "Use when the customer wants a shipping quote and you have "
                "weight and dimensions."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Reason for delegation",
                    },
                },
                "required": [],
            },
            handler=handlers.delegate_to_quote_agent,
            timeout_seconds=3.0,
            enabled=True,
            tags=("delegation",),
        ),
        ToolSpec(
            name="calculate_shipping_quote",
            description=(
                "Calculate shipping cost based on weight and dimensions. "
                "Returns an estimate in VND. Requires weight_kg and all three "
                "dimensions. Supports service types: nhanh, thuong, bo, bolo."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "weight_kg": {
                        "type": "number",
                        "description": "Package weight in kg",
                    },
                    "length_cm": {
                        "type": "number",
                        "description": "Package length in cm",
                    },
                    "width_cm": {
                        "type": "number",
                        "description": "Package width in cm",
                    },
                    "height_cm": {
                        "type": "number",
                        "description": "Package height in cm",
                    },
                    "service_type": {
                        "type": "string",
                        "enum": ["nhanh", "thuong", "bo", "bolo"],
                        "description": (
                            "Service tier: nhanh (3-6 days), thuong (5-10 days), "
                            "bo (10-15 days), bolo (15-25 days, batch)"
                        ),
                    },
                },
                "required": ["weight_kg", "length_cm", "width_cm", "height_cm"],
            },
            handler=handlers.calculate_shipping_quote,
            timeout_seconds=5.0,
            enabled=True,
            tags=("shipping", "quote"),
        ),
    ]

    for spec in specs:
        registry.register(spec)

    logger.info("tool_registry_bootstrap", extra={"tool_count": len(specs)})


# ---------------------------------------------------------------------------
# Agent tool sets
# ---------------------------------------------------------------------------

# Tools available to the main conversational agent
MAIN_AGENT_TOOLS = frozenset({
    "lookup_customer",
    "get_order_status",
    "create_support_ticket",
    "handoff_request",
    "delegate_to_quote_agent",
})

# Tools available to the quote sub-agent
QUOTE_AGENT_TOOLS = frozenset({
    "calculate_shipping_quote",
})
