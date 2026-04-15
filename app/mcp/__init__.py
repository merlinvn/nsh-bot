"""MCP layer — per-domain tools routed through a remote MCP HTTP server.

Architecture:
- app.mcp.server: Standalone FastAPI HTTP server (runs as nsh-mcp container)
  serves all domain tools via JSON-RPC 2.0 over HTTP
- app.mcp.client: MCPHTTPClient, MCPHTTPBackend — HTTP client for remote MCP server
- app.mcp.tools: Shipping tool definitions (calculate_shipping_quote)
- app.mcp.customer: Customer tool definitions and handlers (lookup_customer, get_order_status)
- app.mcp.support: Support tool definitions and handlers (create_support_ticket, handoff_request)
- app.mcp.engine: Pricing engine binding for shipping tools
- app.mcp.pricing: Pure pricing engine (QuoteInput → QuoteResult, no MCP deps)
"""

from app.mcp.client import MCPClient, MCPHTTPBackend, MCPHTTPClient

__all__ = ["MCPClient", "MCPHTTPBackend", "MCPHTTPClient"]
