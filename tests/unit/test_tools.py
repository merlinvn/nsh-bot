"""Tests for MCP domain tools (customer, support, shipping)."""

import pytest

from app.workers.mcp.customer import (
    get_tool_definitions as customer_tool_defs,
    lookup_customer,
    get_order_status,
)
from app.workers.mcp.support import (
    get_tool_definitions as support_tool_defs,
    create_support_ticket,
    handoff_request,
)
from app.workers.mcp.tools import get_mcp_tool_definitions as shipping_tool_defs


# ---------------------------------------------------------------------------
# Customer tools
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lookup_customer_by_phone():
    result = await lookup_customer({"query": "0912345678"})
    assert result["found"] is True
    assert result["customer"]["phone"] == "0912345678"
    assert result["customer"]["name"] == "Nguyen Van A"


@pytest.mark.asyncio
async def test_lookup_customer_by_name():
    result = await lookup_customer({"query": "Tran Thi B"})
    assert result["found"] is True
    assert result["customer"]["name"] == "Tran Thi B"


@pytest.mark.asyncio
async def test_lookup_customer_not_found():
    result = await lookup_customer({"query": "Người không tồn tại"})
    assert result["found"] is False


@pytest.mark.asyncio
async def test_lookup_customer_empty_query():
    result = await lookup_customer({"query": ""})
    assert result["found"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_get_order_status_found():
    result = await get_order_status({"order_id": "ORD-001"})
    assert result["found"] is True
    assert result["order"]["order_id"] == "ORD-001"
    assert result["order"]["status"] == "delivered"


@pytest.mark.asyncio
async def test_get_order_status_not_found():
    result = await get_order_status({"order_id": "ORD-INVALID"})
    assert result["found"] is False


@pytest.mark.asyncio
async def test_get_order_status_empty_id():
    result = await get_order_status({"order_id": ""})
    assert result["found"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# Support tools
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_support_ticket():
    result = await create_support_ticket({
        "subject": "Hoàn tiền đơn hàng",
        "description": "Tôi muốn được hoàn tiền cho đơn hàng ORD-001",
        "priority": "high",
    })
    assert result["success"] is True
    assert "ticket_id" in result
    assert result["ticket_id"].startswith("TKT-")


@pytest.mark.asyncio
async def test_create_support_ticket_empty_fields():
    result = await create_support_ticket({"subject": "", "description": ""})
    assert result["success"] is True
    assert "ticket_id" in result


@pytest.mark.asyncio
async def test_handoff_request():
    result = await handoff_request({"reason": "Customer explicitly requests human agent"})
    assert result["success"] is True
    assert "chuyển" in result["message"].lower()


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

def test_customer_tool_definitions():
    defs = customer_tool_defs()
    names = {d["name"] for d in defs}
    assert names == {"lookup_customer", "get_order_status"}


def test_support_tool_definitions():
    defs = support_tool_defs()
    names = {d["name"] for d in defs}
    assert names == {"create_support_ticket", "handoff_request"}


def test_shipping_tool_definitions():
    defs = shipping_tool_defs()
    names = {d["name"] for d in defs}
    assert names == {"calculate_shipping_quote", "explain_quote_breakdown"}


def test_all_tool_definitions_have_required_fields():
    for defs in [customer_tool_defs(), support_tool_defs(), shipping_tool_defs()]:
        for tool_def in defs:
            assert "name" in tool_def
            assert "description" in tool_def
            assert "input_schema" in tool_def
            assert "type" in tool_def["input_schema"]
            assert tool_def["input_schema"]["type"] == "object"
