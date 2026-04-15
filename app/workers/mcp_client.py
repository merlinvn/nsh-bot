"""Standalone MCP HTTP client for workers — no app.mcp import.

Workers use plain httpx to call nsh-mcp:8080/rpc.
This module replaces app.mcp.client for use by workers only.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any


DEFAULT_MCP_URL = "http://nsh-mcp:8080"

# Process-level tool definitions cache (fetched once at startup)
_tool_definitions_cache: list[dict[str, Any]] = []
_cache_loaded = False
_cache_lock = threading.Lock()


def _resolve_urls() -> list[str]:
    """Resolve MCP server URLs from MCP_SERVER_URLS env var."""
    env_val = os.environ.get("MCP_SERVER_URLS") or os.environ.get("MCP_SERVER_URL")
    if env_val:
        return [u.rstrip("/") for u in env_val.split(",") if u.strip()]
    return [DEFAULT_MCP_URL]


def list_tools() -> list[dict[str, Any]]:
    """Fetch tool definitions from the first available MCP server (cached)."""
    global _cache_loaded
    if not _cache_loaded:
        with _cache_lock:
            if not _cache_loaded:
                urls = _resolve_urls()
                for url in urls:
                    try:
                        import requests

                        resp = requests.get(f"{url}/rpc", timeout=5)
                        resp.raise_for_status()
                        data = resp.json()
                        if "error" in data:
                            continue
                        tools = data.get("result", {}).get("tools", [])
                        global _tool_definitions_cache
                        _tool_definitions_cache = tools
                        _cache_loaded = True
                        return tools
                    except Exception:
                        continue
                _tool_definitions_cache = []
                _cache_loaded = True
    return _tool_definitions_cache


class _ToolResult:
    """Wrapper — provides .output attribute for AgentRunner compatibility."""

    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output


class MCPToolBackend:
    """Async tool backend — calls nsh-mcp via HTTP JSON-RPC."""

    def __init__(self, base_urls: list[str] | None = None) -> None:
        self._urls = base_urls or _resolve_urls()

    async def call(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        import httpx

        for url in self._urls:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    payload = {
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": tool_input},
                        "id": 1,
                    }
                    resp = await client.post(
                        f"{url}/rpc",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if "error" in data:
                        continue
                    result = data.get("result", {})
                    content = result.get("content", [])
                    if content and content[0].get("type") == "text":
                        return json.loads(content[0]["text"])
                    return result
            except Exception:
                continue
        raise RuntimeError(f"All MCP servers failed for {tool_name}")

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> _ToolResult:
        result = await self.call(tool_name, tool_input)
        return _ToolResult(output=result)
