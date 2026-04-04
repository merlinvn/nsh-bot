"""Tests for the ToolCall model."""
import pytest
from sqlalchemy import select

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.tool_call import ToolCall


class TestToolCall:
    """Tests for ToolCall ORM model."""

    async def _create_message(self, session, **kwargs):
        """Helper to create a conversation and message."""
        conv = Conversation(
            external_user_id=kwargs.get("external_user_id", "user_tc_test"),
            conversation_key=kwargs.get("conversation_key", "tc_conv_key"),
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)

        msg = Message(
            conversation_id=conv.id,
            direction=kwargs.get("direction", "inbound"),
            text=kwargs.get("text", "Test message for tool call"),
            message_id=kwargs.get("message_id", "tc_msg_001"),
            prompt_version=kwargs.get("prompt_version", "v1"),
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return msg

    async def test_create_tool_call_linked_to_message(self, session):
        """Can create tool_call linked to message via FK."""
        msg = await self._create_message(session)

        tool_call = ToolCall(
            message_id=msg.id,
            tool_name="lookup_customer",
            input={"query": "customer_123"},
            output={"name": "John Doe", "email": "john@example.com"},
            success=True,
            latency_ms=45,
        )
        session.add(tool_call)
        await session.commit()

        assert tool_call.id is not None
        assert tool_call.message_id == msg.id
        assert tool_call.tool_name == "lookup_customer"

    async def test_tool_name_from_whitelist(self, session):
        """tool_name accepts values from the configured whitelist."""
        msg = await self._create_message(session, message_id="tc_msg_whitelist")

        whitelisted_names = [
            "lookup_customer",
            "get_order_status",
            "create_support_ticket",
            "handoff_request",
        ]
        for name in whitelisted_names:
            tc = ToolCall(
                message_id=msg.id,
                tool_name=name,
                input={},
                output={},
                success=True,
                latency_ms=10,
            )
            session.add(tc)

        await session.commit()

        stmt = select(ToolCall).where(ToolCall.message_id == msg.id)
        result = await session.execute(stmt)
        tool_calls = list(result.scalars().all())
        assert len(tool_calls) == 4
        names = {tc.tool_name for tc in tool_calls}
        assert names == set(whitelisted_names)

    async def test_input_and_output_stored_as_jsonb(self, session):
        """input and output are stored as JSONB (dict)."""
        msg = await self._create_message(session, message_id="tc_msg_jsonb")

        input_data = {"order_id": "ORD-999", "include_history": True}
        output_data = {
            "order_id": "ORD-999",
            "status": "shipped",
            "items": [{"sku": "A1", "qty": 2}],
        }

        tool_call = ToolCall(
            message_id=msg.id,
            tool_name="get_order_status",
            input=input_data,
            output=output_data,
            success=True,
            latency_ms=100,
        )
        session.add(tool_call)
        await session.commit()

        await session.refresh(tool_call)
        assert tool_call.input == input_data
        assert tool_call.output == output_data
        assert tool_call.output["items"][0]["sku"] == "A1"

    async def test_success_is_boolean(self, session):
        """success is a boolean field."""
        msg = await self._create_message(session, message_id="tc_msg_success")

        successful_tc = ToolCall(
            message_id=msg.id,
            tool_name="lookup_customer",
            input={},
            output={"found": True},
            success=True,
            latency_ms=20,
        )
        failed_tc = ToolCall(
            message_id=msg.id,
            tool_name="lookup_customer",
            input={},
            output={"error": "Customer not found"},
            success=False,
            latency_ms=20,
        )
        session.add_all([successful_tc, failed_tc])
        await session.commit()

        assert successful_tc.success is True
        assert failed_tc.success is False

    async def test_error_is_optional_text(self, session):
        """error field is optional text."""
        msg = await self._create_message(session, message_id="tc_msg_error")

        tc_with_error = ToolCall(
            message_id=msg.id,
            tool_name="lookup_customer",
            input={},
            output={},
            success=False,
            error="Timeout: upstream service unavailable",
            latency_ms=5000,
        )
        tc_without_error = ToolCall(
            message_id=msg.id,
            tool_name="lookup_customer",
            input={},
            output={"found": False},
            success=True,
            latency_ms=10,
            error=None,
        )
        session.add_all([tc_with_error, tc_without_error])
        await session.commit()

        assert tc_with_error.error == "Timeout: upstream service unavailable"
        assert tc_without_error.error is None

    async def test_latency_ms_stored(self, session):
        """latency_ms is stored as an integer."""
        msg = await self._create_message(session, message_id="tc_msg_lat")

        tool_call = ToolCall(
            message_id=msg.id,
            tool_name="handoff_request",
            input={"reason": "escalation"},
            output={"ticket_id": "T-123"},
            success=True,
            latency_ms=1234,
        )
        session.add(tool_call)
        await session.commit()

        await session.refresh(tool_call)
        assert tool_call.latency_ms == 1234
        assert isinstance(tool_call.latency_ms, int)
