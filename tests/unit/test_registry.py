"""Tests for the tool registry, backend, and handlers."""

import pytest

from app.workers.conversation import handlers
from app.workers.conversation.registry import (
    MAIN_AGENT_TOOLS,
    QUOTE_AGENT_TOOLS,
    ToolRegistry,
    ToolSpec,
    LocalToolBackend,
    get_registry,
)
from app.workers.conversation.tools_models import (
    LookupCustomerInput,
    CreateSupportTicketInput,
    CalculateShippingQuoteInput,
    DelegateToQuoteAgentInput,
)


# ---------------------------------------------------------------------------
# ToolSpec tests
# ---------------------------------------------------------------------------

def test_tool_spec_defaults():
    """ToolSpec has correct default values."""
    spec = ToolSpec(
        name="test",
        description="A test",
        input_model=LookupCustomerInput,
        handler=handlers.lookup_customer,
    )
    assert spec.timeout_seconds == 5.0
    assert spec.enabled is True
    assert spec.tags == ()


def test_tool_spec_custom_values():
    """ToolSpec accepts custom timeout, enabled, and tags."""
    spec = ToolSpec(
        name="test",
        description="A test",
        input_model=LookupCustomerInput,
        handler=handlers.lookup_customer,
        timeout_seconds=10.0,
        enabled=False,
        tags=("quote", "shipping"),
    )
    assert spec.timeout_seconds == 10.0
    assert spec.enabled is False
    assert spec.tags == ("quote", "shipping")


# ---------------------------------------------------------------------------
# ToolRegistry tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_and_get_tool():
    """register() stores spec; get() retrieves it."""
    registry = ToolRegistry()
    spec = ToolSpec(
        name="test_tool",
        description="A test tool",
        input_model=LookupCustomerInput,
        handler=handlers.lookup_customer,
    )
    registry.register(spec)
    retrieved = registry.get("test_tool")
    assert retrieved is not None
    assert retrieved.name == "test_tool"


@pytest.mark.asyncio
async def test_get_nonexistent_tool():
    """get() returns None for unknown tool."""
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None


@pytest.mark.asyncio
async def test_register_duplicate_raises():
    """Registering the same tool name twice raises KeyError."""
    registry = ToolRegistry()
    spec = ToolSpec(
        name="dup_tool",
        description="A test",
        input_model=LookupCustomerInput,
        handler=handlers.lookup_customer,
    )
    registry.register(spec)
    with pytest.raises(KeyError, match="dup_tool"):
        registry.register(spec)


@pytest.mark.asyncio
async def test_definitions_returns_all_enabled_by_default():
    """definitions() returns all enabled tools with no filter."""
    registry = ToolRegistry()
    registry.register(ToolSpec(name="a", description="", input_model=LookupCustomerInput, handler=handlers.lookup_customer, enabled=True))
    registry.register(ToolSpec(name="b", description="", input_model=CreateSupportTicketInput, handler=handlers.get_order_status, enabled=True))
    defs = registry.definitions()
    names = {d["name"] for d in defs}
    assert names == {"a", "b"}


@pytest.mark.asyncio
async def test_definitions_filters_by_allowed_names():
    """definitions(allowed_names=...) excludes tools not in the set."""
    registry = ToolRegistry()
    registry.register(ToolSpec(name="tool_a", description="", input_model=LookupCustomerInput, handler=handlers.lookup_customer, enabled=True))
    registry.register(ToolSpec(name="tool_b", description="", input_model=CreateSupportTicketInput, handler=handlers.get_order_status, enabled=True))
    defs = registry.definitions(allowed_names={"tool_a"})
    assert len(defs) == 1
    assert defs[0]["name"] == "tool_a"


@pytest.mark.asyncio
async def test_definitions_excludes_disabled_by_default():
    """definitions() excludes disabled tools."""
    registry = ToolRegistry()
    registry.register(ToolSpec(name="enabled_tool", description="", input_model=LookupCustomerInput, handler=handlers.lookup_customer, enabled=True))
    registry.register(ToolSpec(name="disabled_tool", description="", input_model=CreateSupportTicketInput, handler=handlers.get_order_status, enabled=False))
    defs = registry.definitions()
    names = {d["name"] for d in defs}
    assert "enabled_tool" in names
    assert "disabled_tool" not in names


@pytest.mark.asyncio
async def test_definitions_includes_disabled_when_flagged():
    """definitions(include_disabled=True) includes disabled tools."""
    registry = ToolRegistry()
    registry.register(ToolSpec(name="disabled_tool", description="", input_model=LookupCustomerInput, handler=handlers.lookup_customer, enabled=False))
    defs = registry.definitions(include_disabled=True)
    assert any(d["name"] == "disabled_tool" for d in defs)


# ---------------------------------------------------------------------------
# LocalToolBackend tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_local_backend_calls_handler():
    """LocalToolBackend.call() runs the registered handler."""
    registry = ToolRegistry()
    spec = ToolSpec(
        name="lookup_customer",
        description="",
        input_model=LookupCustomerInput,
        handler=handlers.lookup_customer,
        timeout_seconds=5.0,
        enabled=True,
    )
    registry.register(spec)
    backend = LocalToolBackend(registry)
    result = await backend.call("lookup_customer", {"query": "0912345678"})
    assert result["found"] is True
    assert result["customer"]["phone"] == "0912345678"


@pytest.mark.asyncio
async def test_local_backend_unknown_tool_raises():
    """LocalToolBackend.call() raises ValueError for unknown tool."""
    registry = ToolRegistry()
    backend = LocalToolBackend(registry)
    with pytest.raises(ValueError, match="Unknown tool"):
        await backend.call("nonexistent_tool", {})


@pytest.mark.asyncio
async def test_local_backend_disabled_tool_raises():
    """LocalToolBackend.call() raises ValueError for disabled tool."""
    registry = ToolRegistry()
    spec = ToolSpec(
        name="disabled_tool",
        description="",
        input_model=LookupCustomerInput,
        handler=handlers.lookup_customer,
        enabled=False,
    )
    registry.register(spec)
    backend = LocalToolBackend(registry)
    with pytest.raises(ValueError, match="Disabled tool"):
        await backend.call("disabled_tool", {})


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_global_registry_is_singleton():
    """get_registry() returns the same instance on repeated calls."""
    reg1 = get_registry()
    reg2 = get_registry()
    assert reg1 is reg2


@pytest.mark.asyncio
async def test_global_registry_has_phase1_tools():
    """Global registry is pre-populated with Phase 1 tools."""
    registry = get_registry()
    for tool_name in ["lookup_customer", "get_order_status", "create_support_ticket", "handoff_request"]:
        assert registry.get(tool_name) is not None, f"{tool_name} not found in registry"


# ---------------------------------------------------------------------------
# Agent tool set constants
# ---------------------------------------------------------------------------

def test_main_agent_tools_has_expected():
    """MAIN_AGENT_TOOLS contains all expected tool names."""
    assert "lookup_customer" in MAIN_AGENT_TOOLS
    assert "get_order_status" in MAIN_AGENT_TOOLS
    assert "create_support_ticket" in MAIN_AGENT_TOOLS
    assert "handoff_request" in MAIN_AGENT_TOOLS
    assert "delegate_to_quote_agent" in MAIN_AGENT_TOOLS


def test_quote_agent_tools():
    """QUOTE_AGENT_TOOLS contains calculate_shipping_quote."""
    assert "calculate_shipping_quote" in QUOTE_AGENT_TOOLS


# ---------------------------------------------------------------------------
# Handler tests (delegate_to_quote_agent, calculate_shipping_quote)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delegate_to_quote_agent():
    """delegate_to_quote_agent returns delegation instruction."""
    result = await handlers.delegate_to_quote_agent(DelegateToQuoteAgentInput())
    assert result["delegated"] is True
    assert "calculate_shipping_quote" in result["message"]


@pytest.mark.asyncio
async def test_calculate_shipping_quote_nhanh():
    """calculate_shipping_quote computes correct estimate for 'nhanh'."""
    result = await handlers.calculate_shipping_quote(CalculateShippingQuoteInput(
        weight_kg=5.0,
        length_cm=30,
        width_cm=20,
        height_cm=10,
        service_type="nhanh",
    ))
    assert result["success"] is True
    assert result["service_type"] == "nhanh"
    assert "estimated_total_vnd" in result


@pytest.mark.asyncio
async def test_calculate_shipping_quote_bolo():
    """calculate_shipping_quote applies minimum charge for bolo."""
    result = await handlers.calculate_shipping_quote(CalculateShippingQuoteInput(
        weight_kg=1.0,
        length_cm=10,
        width_cm=10,
        height_cm=10,
        service_type="bolo",
    ))
    assert result["success"] is True
    # 0.0002 m³ * 250 = 0.05kg < 50kg minimum → should be 50kg
    assert result["chargeable_kg"] == 50.0


@pytest.mark.asyncio
async def test_calculate_shipping_quote_missing_weight():
    """calculate_shipping_quote rejects missing weight."""
    with pytest.raises(Exception):  # Pydantic validation error
        CalculateShippingQuoteInput(
            length_cm=30,
            width_cm=20,
            height_cm=10,
            service_type="thuong",
        )


@pytest.mark.asyncio
async def test_calculate_shipping_quote_unknown_service():
    """calculate_shipping_quote rejects unknown service type."""
    with pytest.raises(Exception):  # Pydantic validation error
        CalculateShippingQuoteInput(
            weight_kg=5.0,
            length_cm=30,
            width_cm=20,
            height_cm=10,
            service_type="invalid_type",
        )
