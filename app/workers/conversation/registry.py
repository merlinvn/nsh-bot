"""Tool registry and backend protocol for the conversation worker.

Architecture:
- ToolSpec: dataclass with Pydantic input model, handler, timeout, tags
- ToolBackend: Protocol — interface for calling tools (local or remote/MCP)
- LocalToolBackend: validates input via Pydantic, then calls handler
- ToolRegistry: manages tool registration and exposes LLM-compatible definitions
- get_registry(): singleton accessor, bootstraps defaults on first call

This enables:
- Multiple agent tool sets (MAIN_AGENT_TOOLS, QUOTE_AGENT_TOOLS)
- Multi-tenant tool filtering per agent/tenant
- Swap LocalToolBackend for MCPToolBackend without changing executor
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, Type

from pydantic import BaseModel

from app.workers.shared.logging import get_logger

logger = get_logger("conversation-worker.registry")

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ToolHandler = Callable[[BaseModel], Awaitable[dict]]


# ---------------------------------------------------------------------------
# ToolSpec
# ---------------------------------------------------------------------------

@dataclass
class ToolSpec:
    """Specification for a single tool.

    Attributes:
        name: Unique tool identifier.
        description: Human-readable description for the LLM.
        input_model: Pydantic BaseModel subclass for input validation.
            The handler receives an instance of this model.
        handler: Async callable that receives the validated input model.
        timeout_seconds: Max execution time before TimeoutError is raised.
        enabled: Whether the tool is active (excluded from definitions when False).
        tags: Arbitrary labels for grouping/filtering (e.g. "customer", "quote").
    """
    name: str
    description: str
    input_model: Type[BaseModel]
    handler: ToolHandler
    timeout_seconds: float = 5.0
    enabled: bool = True
    tags: tuple[str, ...] = ()

    def definition(self) -> dict[str, Any]:
        """Return LLM tool definition derived from the Pydantic input model."""
        schema = self.input_model.model_json_schema()
        # Strip verbose title that Pydantic adds
        schema.pop("title", None)
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": schema,
        }


# ---------------------------------------------------------------------------
# ToolBackend protocol
# ---------------------------------------------------------------------------

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
# LocalToolBackend
# ---------------------------------------------------------------------------

class LocalToolBackend:
    """Validates input via Pydantic then calls the registered handler."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def call(self, tool_name: str, tool_input: dict) -> dict:
        """Look up the tool, validate input, and run its handler."""
        spec = self._registry.get(tool_name)
        if spec is None:
            raise ValueError(f"Unknown tool: {tool_name}")
        if not spec.enabled:
            raise ValueError(f"Disabled tool: {tool_name}")

        # Validate input with Pydantic before calling handler
        parsed = spec.input_model.model_validate(tool_input)

        return await asyncio.wait_for(
            spec.handler(parsed),
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
        """Return LLM tool definitions for all (or allowed) tools.

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
            result.append(spec.definition())
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
    from app.workers.conversation import handlers
    from app.workers.conversation.tools_models import (
        CalculateShippingQuoteInput,
        CreateSupportTicketInput,
        DelegateToQuoteAgentInput,
        GetOrderStatusInput,
        HandoffRequestInput,
        LookupCustomerInput,
    )

    specs = [
        ToolSpec(
            name="lookup_customer",
            description=(
                "Find customer by phone number or name. Use this when a customer "
                "provides their phone number or name and you need to look up "
                "their account information."
            ),
            input_model=LookupCustomerInput,
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
            input_model=GetOrderStatusInput,
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
            input_model=CreateSupportTicketInput,
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
            input_model=HandoffRequestInput,
            handler=handlers.handoff_request,
            timeout_seconds=3.0,
            enabled=True,
            tags=("handoff",),
        ),
        ToolSpec(
            name="delegate_to_quote_agent",
            description=(
                "Delegate to the quote subagent to calculate shipping rates. "
                "Use when the customer wants a shipping quote. "
                "Pass customer_message and any known_context (weight, dimensions, service_type)."
            ),
            input_model=DelegateToQuoteAgentInput,
            handler=handlers.delegate_to_quote_agent,
            timeout_seconds=3.0,
            enabled=True,
            tags=("delegation",),
        ),
        ToolSpec(
            name="calculate_shipping_quote",
            description=(
                "Calculate shipping cost based on weight, dimensions, and service type. "
                "Returns a structured quote with status, message_to_customer, and quote_data. "
                "Supports service types: fast, standard, bundle, lot."
            ),
            input_model=CalculateShippingQuoteInput,
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

MAIN_AGENT_TOOLS = frozenset({
    "lookup_customer",
    "get_order_status",
    "create_support_ticket",
    "handoff_request",
    "delegate_to_quote_agent",
})

QUOTE_AGENT_TOOLS = frozenset({
    "calculate_shipping_quote",
})
