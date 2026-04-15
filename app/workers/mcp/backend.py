"""MCPToolBackend — now a thin alias to MCPHTTPBackend.

The actual execution is done by the remote MCP HTTP server.
MCPToolBackend is kept as the type alias for backward compatibility.

This module is DEPRECATED — use app.workers.mcp.client directly:
- MCPClient.list_tools() — tool definitions
- MCPClient.backend — async tool execution backend
"""

from __future__ import annotations

from app.workers.mcp.client import MCPHTTPBackend as MCPToolBackend

# For backward compatibility with imports of ToolExecutor
ToolExecutor = MCPToolBackend
