"""Backward-compatible tool exports.

All tool execution now goes through app.workers.mcp.
This module re-exports for backward compatibility with existing imports.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.workers.mcp.backend import MCPToolBackend

# Alias so existing code that imports ToolExecutor still works.
# MCPToolBackend is the single tool execution backend.
ToolExecutor = MCPToolBackend


@dataclass
class ToolResult:
    """Result from a tool execution."""
    output: dict
    success: bool
