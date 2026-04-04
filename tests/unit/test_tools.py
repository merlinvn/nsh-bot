"""Tests for the tool registry and executors."""
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.conversation.tools import (
    TOOL_DEFINITIONS,
    TOOL_WHITELIST,
    ToolExecutor,
    ToolResult,
)


@pytest.mark.asyncio
async def test_lookup_customer_tool():
    """Execute lookup_customer tool with phone query."""
    executor = ToolExecutor()
    result = await executor.execute("lookup_customer", {"query": "0912345678"})

    assert result.success is True
    assert result.output["found"] is True
    assert result.output["customer"]["phone"] == "0912345678"
    assert result.output["customer"]["name"] == "Nguyen Van A"


@pytest.mark.asyncio
async def test_lookup_customer_by_name():
    """Execute lookup_customer tool with name query."""
    executor = ToolExecutor()
    result = await executor.execute("lookup_customer", {"query": "Tran Thi B"})

    assert result.success is True
    assert result.output["found"] is True
    assert result.output["customer"]["name"] == "Tran Thi B"


@pytest.mark.asyncio
async def test_lookup_customer_not_found():
    """Execute lookup_customer with unknown query."""
    executor = ToolExecutor()
    result = await executor.execute("lookup_customer", {"query": "Người không tồn tại"})

    assert result.success is True  # Tool succeeds, returns not found
    assert result.output["found"] is False


@pytest.mark.asyncio
async def test_lookup_customer_empty_query():
    """Execute lookup_customer with empty query."""
    executor = ToolExecutor()
    result = await executor.execute("lookup_customer", {"query": ""})

    assert result.success is True
    assert result.output["found"] is False
    assert "error" in result.output


@pytest.mark.asyncio
async def test_get_order_status_tool():
    """Execute get_order_status with order_id."""
    executor = ToolExecutor()
    result = await executor.execute("get_order_status", {"order_id": "ORD-001"})

    assert result.success is True
    assert result.output["found"] is True
    assert result.output["order"]["order_id"] == "ORD-001"
    assert result.output["order"]["status"] == "delivered"


@pytest.mark.asyncio
async def test_get_order_status_not_found():
    """Execute get_order_status with unknown order_id."""
    executor = ToolExecutor()
    result = await executor.execute("get_order_status", {"order_id": "ORD-INVALID"})

    assert result.success is True
    assert result.output["found"] is False


@pytest.mark.asyncio
async def test_get_order_status_empty_id():
    """Execute get_order_status with empty order_id."""
    executor = ToolExecutor()
    result = await executor.execute("get_order_status", {"order_id": ""})

    assert result.success is True
    assert result.output["found"] is False
    assert "error" in result.output


@pytest.mark.asyncio
async def test_create_support_ticket_tool():
    """Execute create_support_ticket."""
    executor = ToolExecutor()
    result = await executor.execute(
        "create_support_ticket",
        {
            "subject": "Hoàn tiền đơn hàng",
            "description": "Tôi muốn được hoàn tiền cho đơn hàng ORD-001",
            "priority": "high",
        },
    )

    assert result.success is True
    assert result.output["success"] is True
    assert "ticket_id" in result.output
    assert result.output["ticket_id"].startswith("TKT-")


@pytest.mark.asyncio
async def test_create_support_ticket_missing_fields():
    """Execute create_support_ticket without required fields."""
    executor = ToolExecutor()
    result = await executor.execute("create_support_ticket", {"subject": "", "description": ""})

    assert result.success is True
    assert result.output["success"] is False


@pytest.mark.asyncio
async def test_handoff_request_tool():
    """Execute handoff_request."""
    executor = ToolExecutor()
    result = await executor.execute(
        "handoff_request",
        {"reason": "Customer explicitly requests human agent"},
    )

    assert result.success is True
    assert result.output["success"] is True
    assert "chuyển" in result.output["message"].lower()


@pytest.mark.asyncio
async def test_unknown_tool_raises():
    """Execute unknown tool name."""
    executor = ToolExecutor()
    result = await executor.execute("nonexistent_tool", {"arg": "value"})

    assert result.success is False
    assert "Unknown tool" in result.output["error"]


def test_tool_whitelist_contains_expected_tools():
    """Verify the tool whitelist has the expected entries."""
    assert "lookup_customer" in TOOL_WHITELIST
    assert "get_order_status" in TOOL_WHITELIST
    assert "create_support_ticket" in TOOL_WHITELIST
    assert "handoff_request" in TOOL_WHITELIST
    assert len(TOOL_WHITELIST) == 4


def test_tool_definitions_count():
    """Verify tool definitions match whitelist count."""
    assert len(TOOL_DEFINITIONS) == len(TOOL_WHITELIST)


def test_tool_definitions_have_required_fields():
    """Verify each tool definition has required schema fields."""
    for tool_def in TOOL_DEFINITIONS:
        assert "name" in tool_def
        assert "description" in tool_def
        assert "input_schema" in tool_def
        assert tool_def["name"] in TOOL_WHITELIST
        assert "type" in tool_def["input_schema"]
        assert tool_def["input_schema"]["type"] == "object"
