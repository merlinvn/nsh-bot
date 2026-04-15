"""Support MCP server — create_support_ticket, handoff_request."""

from __future__ import annotations

import uuid
from typing import Any

from app.workers.shared.logging import get_logger

logger = get_logger("mcp.support")

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

CREATE_SUPPORT_TICKET_DESCRIPTION = (
    "Open a customer support ticket. "
    "Use when customer reports an issue that needs follow-up. "
    "Creates a ticket with subject, description, and priority."
)

HANDOFF_REQUEST_DESCRIPTION = (
    "Request human agent handoff. "
    "Use when customer explicitly asks for a human, or when the AI cannot resolve the issue. "
    "Flags the conversation for priority human attention."
)


def get_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "create_support_ticket",
            "description": CREATE_SUPPORT_TICKET_DESCRIPTION,
            "input_schema": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Brief subject/summary of the issue",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of the issue",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "default": "medium",
                        "description": "Ticket priority level",
                    },
                },
                "required": ["subject", "description"],
            },
        },
        {
            "name": "handoff_request",
            "description": HANDOFF_REQUEST_DESCRIPTION,
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Reason for the handoff request",
                    },
                },
                "required": ["reason"],
            },
        },
    ]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def create_support_ticket(input: dict[str, Any]) -> dict[str, Any]:
    """Open a support ticket."""
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"

    logger.info(
        "support_ticket_created",
        extra={
            "ticket_id": ticket_id,
            "subject": input.get("subject"),
            "priority": input.get("priority", "medium"),
        },
    )

    return {
        "success": True,
        "ticket_id": ticket_id,
        "message": f"Đã tạo phiếu hỗ trợ #{ticket_id}. Chúng tôi sẽ liên hệ sớm.",
    }


async def handoff_request(input: dict[str, Any]) -> dict[str, Any]:
    """Flag conversation for human handoff."""
    logger.info(
        "handoff_requested",
        extra={"reason": input.get("reason")},
    )

    return {
        "success": True,
        "message": "Yêu cầu chuyển đã được ghi nhận. Đại diện chăm sóc khách hàng sẽ liên hệ sớm.",
        "estimated_wait": "5-10 phút",
    }
