"""Standalone MCP HTTP server — JSON-RPC 2.0 over HTTP.

Runs as a separate Docker service. All domain tools are registered here:
- Shipping: calculate_shipping_quote, explain_quote_breakdown
- Customer: lookup_customer, get_order_status
- Support: create_support_ticket, handoff_request

Serves:
- POST /rpc  — tools/call
- GET /rpc   — tools/list (returns all tool definitions)
- GET /health — liveness
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.workers.mcp import engine as shipping_engine
from app.workers.mcp import customer, support

app = FastAPI(title="nsh-mcp")

TOOL_HANDLERS: dict[str, Any] = {
    # Shipping tools (engine)
    "calculate_shipping_quote": shipping_engine.mcp_calculate_shipping_quote,
    "explain_quote_breakdown": shipping_engine.mcp_explain_quote_breakdown,
    # Customer tools
    "lookup_customer": customer.lookup_customer,
    "get_order_status": customer.get_order_status,
    # Support tools
    "create_support_ticket": support.create_support_ticket,
    "handoff_request": support.handoff_request,
}


def _get_tool_definitions() -> list[dict[str, Any]]:
    from app.workers.mcp.tools import get_mcp_tool_definitions as shipping_tools
    return shipping_tools() + customer.get_tool_definitions() + support.get_tool_definitions()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/rpc")
async def list_tools(request: Request) -> JSONResponse:
    """tools/list — returns all available tool definitions."""
    id_val = request.query_params.get("id", None)

    return JSONResponse(
        content={
            "jsonrpc": "2.0",
            "result": {"tools": _get_tool_definitions()},
            "id": id_val,
        }
    )


@app.post("/rpc")
async def handle_rpc(request: Request) -> JSONResponse:
    """Handle all JSON-RPC 2.0 requests.

    Supports:
    - tools/list: list all tool definitions
    - tools/call: execute a tool by name
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None,
            },
            status_code=400,
        )

    method: str = body.get("method", "")
    params: dict[str, Any] = body.get("params", {})
    id_val: Any = body.get("id")

    # tools/list
    if method == "tools/list":
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "result": {"tools": _get_tool_definitions()},
                "id": id_val,
            }
        )

    # tools/call
    if method == "tools/call":
        tool_name: str = params.get("name", "")
        tool_input: dict[str, Any] = params.get("arguments", {})

        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32602,
                        "message": f"Unknown tool: {tool_name}",
                        "data": {"tool": tool_name},
                    },
                    "id": id_val,
                },
                status_code=200,
            )

        try:
            # Shipping tools need redis + tenant_id
            if tool_name in ("calculate_shipping_quote", "explain_quote_breakdown"):
                tenant_id = params.get("tenant_id", "nsh")
                redis_client = redis.from_url(
                    "redis://redis:6379",
                    encoding="utf-8",
                    decode_responses=False,
                )
                result = await handler(
                    redis_client,
                    tool_input,
                    tenant_id=tenant_id,
                )
            else:
                result = await handler(tool_input)

            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                    },
                    "id": id_val,
                }
            )
        except Exception as e:
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {e}",
                        "data": {"tool": tool_name},
                    },
                    "id": id_val,
                },
                status_code=200,
            )

    # Unknown method
    return JSONResponse(
        content={
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Method not found: {method}"},
            "id": id_val,
        },
        status_code=200,
    )
