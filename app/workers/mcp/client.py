"""MCP HTTP client — calls remote MCP server(s) over HTTP JSON-RPC 2.0.

Supports multiple MCP server URLs (comma-separated in MCP_SERVER_URLS env var).
Agent tries each URL in order and uses the first successful one.

Example:
  MCP_SERVER_URLS=http://nsh-mcp:8080,http://backup-mcp:8080
"""

from __future__ import annotations

import json
import threading
from typing import Any

import httpx
import requests

from app.core.config import settings
from app.workers.shared.logging import get_logger

logger = get_logger("mcp.client")

DEFAULT_MCP_URL = "http://nsh-mcp:8080"

# Process-level tool definitions cache (fetched once at startup)
_tool_definitions_cache: list[dict[str, Any]] = []
_cache_loaded = False
_cache_lock = threading.Lock()


def _resolve_urls() -> list[str]:
    """Resolve MCP server URLs from settings."""
    env_val = getattr(settings, "mcp_server_urls", None) or getattr(settings, "mcp_server_url", None)
    if env_val:
        urls = [u.strip() for u in env_val.split(",") if u.strip()]
        return [u.rstrip("/") for u in urls]
    return [DEFAULT_MCP_URL]


def _fetch_tools_sync() -> list[dict[str, Any]]:
    """Fetch tool definitions synchronously (called once at module import)."""
    urls = _resolve_urls()
    errors = []
    for url in urls:
        try:
            response = requests.get(f"{url}/rpc", timeout=5)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                errors.append(f"{url}: {data['error']}")
                continue
            tools = data.get("result", {}).get("tools", [])
            logger.info("mcp_tools_cached", extra={"url": url, "tool_count": len(tools)})
            return tools
        except Exception as e:
            errors.append(f"{url}: {e}")
    logger.error("mcp_tools_fetch_all_failed", extra={"errors": errors})
    return []


def _load_tools() -> list[dict[str, Any]]:
    """Thread-safe one-time tool loader."""
    global _cache_loaded
    if not _cache_loaded:
        with _cache_lock:
            if not _cache_loaded:
                # Fetch synchronously using requests (safe at import time)
                tools = _fetch_tools_sync()
                global _tool_definitions_cache
                _tool_definitions_cache = tools
                _cache_loaded = True
    return _tool_definitions_cache


class MCPHTTPClient:
    """HTTP client for calling a remote MCP server (async, for runtime tool calls)."""

    def __init__(self, base_urls: list[str] | None = None) -> None:
        self._urls = base_urls or _resolve_urls()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def call_tool(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Call tools/call on the first available MCP server."""
        errors = []
        for url in self._urls:
            try:
                client = await self._get_client()
                payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": tool_input,
                    },
                    "id": 1,
                }
                response = await client.post(
                    f"{url}/rpc",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
                if "error" in data:
                    errors.append(f"{url}: {data['error']}")
                    continue
                result = data.get("result", {})
                content = result.get("content", [])
                if content and content[0].get("type") == "text":
                    return json.loads(content[0]["text"])
                return result
            except Exception as e:
                errors.append(f"{url}: {e}")
        logger.error("mcp_call_tool_all_failed", extra={"tool": tool_name, "errors": errors})
        raise RuntimeError(f"All MCP servers failed for {tool_name}: {errors}")


class MCPHTTPBackend:
    """Async tool backend that calls the remote MCP server(s) via HTTP."""

    def __init__(self, base_urls: list[str] | None = None) -> None:
        self._http = MCPHTTPClient(base_urls=base_urls)

    async def call(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        return await self._http.call_tool(tool_name, tool_input)

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Alias of call() for ToolExecutor interface compatibility."""
        return await self.call(tool_name, tool_input)

    async def close(self) -> None:
        await self._http.close()


class MCPClient:
    """MCP client for LLMProcessor.

    Provides:
    - list_tools() — cached tool definitions (sync, safe to call from anywhere)
    - backend — MCPHTTPBackend for async tool execution
    """

    def __init__(self) -> None:
        pass

    def list_tools(self) -> list[dict[str, Any]]:
        """Return cached tool definitions.

        Fetched once at first call (from any thread/async context) using sync requests.
        Thread-safe and async-context-safe.
        """
        return _load_tools()

    @property
    def backend(self) -> MCPHTTPBackend:
        """Async backend for AgentRunner tool execution."""
        return MCPHTTPBackend(base_urls=_resolve_urls())
