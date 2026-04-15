"""Backward-compatible tool exports.

All tool execution now goes through the remote MCP HTTP server.
This module re-exports for backward compatibility with existing imports.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.workers.mcp.client import MCPHTTPBackend

# Alias so existing code that imports ToolExecutor still works.
# MCPHTTPBackend calls the remote MCP server over HTTP.
ToolExecutor = MCPHTTPBackend


@dataclass
class ToolResult:
    """Result from a tool execution."""
    output: dict
    success: bool
