"""MCP layer — per-domain tools routed through a remote MCP HTTP server.

Architecture:
- app.workers.mcp.server: Standalone FastAPI HTTP server (runs as nsh-mcp container)
  serves all domain tools via JSON-RPC 2.0 over HTTP
- app.workers.mcp.client: MCPHTTPClient, MCPHTTPBackend — HTTP client for remote MCP server
- app.workers.mcp.tools: Shipping tool definitions (calculate_shipping_quote, explain_quote_breakdown)
- app.workers.mcp.customer: Customer tool definitions and handlers (lookup_customer, get_order_status)
- app.workers.mcp.support: Support tool definitions and handlers (create_support_ticket, handoff_request)
- app.workers.mcp.engine: Pricing engine binding for shipping tools
"""

from app.workers.mcp.client import MCPClient, MCPHTTPBackend, MCPHTTPClient

__all__ = ["MCPClient", "MCPHTTPBackend", "MCPHTTPClient"]
