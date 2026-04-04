"""Tests for the Message model."""
import pytest
from sqlalchemy import select

from app.models.conversation import Conversation
from app.models.message import Message


class TestMessage:
    """Tests for Message ORM model."""

    async def _create_conversation(self, session, **kwargs):
        """Helper to create a conversation."""
        conv = Conversation(
            external_user_id=kwargs.get("external_user_id", "user_msg_test"),
            conversation_key=kwargs.get("conversation_key", "msg_conv_key"),
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return conv

    async def test_create_message_linked_to_conversation(self, session):
        """Can create message linked to conversation via FK."""
        conv = await self._create_conversation(session)

        message = Message(
            conversation_id=conv.id,
            direction="inbound",
            text="Test message",
            message_id="msg_001",
            prompt_version="v1",
        )
        session.add(message)
        await session.commit()

        assert message.id is not None
        assert message.conversation_id == conv.id
        assert message.text == "Test message"

    async def test_direction_must_be_inbound_or_outbound(self, session):
        """Direction accepts 'inbound' and 'outbound' values."""
        conv = await self._create_conversation(
            session, external_user_id="user_dir", conversation_key="dir_key"
        )

        inbound = Message(
            conversation_id=conv.id,
            direction="inbound",
            text="inbound text",
            message_id="msg_dir_1",
            prompt_version="v1",
        )
        outbound = Message(
            conversation_id=conv.id,
            direction="outbound",
            text="outbound text",
            message_id="msg_dir_2",
            prompt_version="v1",
        )
        session.add_all([inbound, outbound])
        await session.commit()

        assert inbound.direction == "inbound"
        assert outbound.direction == "outbound"

    async def test_token_usage_stored_as_jsonb(self, session):
        """token_usage is stored as JSONB (dict)."""
        conv = await self._create_conversation(
            session, external_user_id="user_token", conversation_key="token_key"
        )

        token_usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }
        message = Message(
            conversation_id=conv.id,
            direction="outbound",
            text="Token usage test",
            message_id="msg_token",
            prompt_version="v1",
            token_usage=token_usage,
        )
        session.add(message)
        await session.commit()

        await session.refresh(message)
        assert message.token_usage == token_usage
        assert message.token_usage["total_tokens"] == 150

    async def test_message_id_for_dedup(self, session):
        """message_id field exists for deduplication."""
        conv = await self._create_conversation(
            session, external_user_id="user_dedup", conversation_key="dedup_key"
        )

        message = Message(
            conversation_id=conv.id,
            direction="inbound",
            text="Dedup test",
            message_id="unique_dedup_id_12345",
            prompt_version="v1",
        )
        session.add(message)
        await session.commit()

        assert message.message_id == "unique_dedup_id_12345"

    async def test_prompt_version_stored(self, session):
        """prompt_version field is stored."""
        conv = await self._create_conversation(
            session, external_user_id="user_pv", conversation_key="pv_key"
        )

        message = Message(
            conversation_id=conv.id,
            direction="inbound",
            text="Prompt version test",
            message_id="msg_pv",
            prompt_version="v2.1.0",
        )
        session.add(message)
        await session.commit()

        assert message.prompt_version == "v2.1.0"

    async def test_latency_ms_stored_as_integer(self, session):
        """latency_ms is stored as an integer."""
        conv = await self._create_conversation(
            session, external_user_id="user_lat", conversation_key="lat_key"
        )

        message = Message(
            conversation_id=conv.id,
            direction="outbound",
            text="Latency test",
            message_id="msg_lat",
            prompt_version="v1",
            latency_ms=1234,
        )
        session.add(message)
        await session.commit()

        await session.refresh(message)
        assert message.latency_ms == 1234
        assert isinstance(message.latency_ms, int)

    async def test_cascade_delete_removes_associated_tool_calls(self, session):
        """Cascade delete removes associated tool_calls when message is deleted."""
        from app.models.tool_call import ToolCall

        conv = await self._create_conversation(
            session, external_user_id="user_cascade_tc", conversation_key="cascade_tc_key"
        )

        message = Message(
            conversation_id=conv.id,
            direction="inbound",
            text="Cascade test",
            message_id="msg_cascade_tc",
            prompt_version="v1",
        )
        session.add(message)
        await session.commit()

        msg_id = message.id
        tool_call = ToolCall(
            message_id=msg_id,
            tool_name="lookup_customer",
            input={"query": "john"},
            output={"found": True},
            success=True,
            latency_ms=50,
        )
        session.add(tool_call)
        await session.commit()

        tc_id = tool_call.id

        # Delete message — tool_call should cascade
        await session.delete(message)
        await session.commit()

        stmt = select(ToolCall).where(ToolCall.id == tc_id)
        result = await session.execute(stmt)
        deleted_tc = result.scalar_one_or_none()
        assert deleted_tc is None

    async def test_cascade_delete_removes_associated_delivery_attempts(self, session):
        """Cascade delete removes associated delivery_attempts when message is deleted."""
        from app.models.delivery_attempt import DeliveryAttempt

        conv = await self._create_conversation(
            session,
            external_user_id="user_cascade_da",
            conversation_key="cascade_da_key",
        )

        message = Message(
            conversation_id=conv.id,
            direction="outbound",
            text="Delivery cascade test",
            message_id="msg_cascade_da",
            prompt_version="v1",
        )
        session.add(message)
        await session.commit()

        msg_id = message.id
        attempt = DeliveryAttempt(
            message_id=msg_id,
            attempt_no=1,
            status="pending",
        )
        session.add(attempt)
        await session.commit()

        da_id = attempt.id

        # Delete message — delivery_attempt should cascade
        await session.delete(message)
        await session.commit()

        stmt = select(DeliveryAttempt).where(DeliveryAttempt.id == da_id)
        result = await session.execute(stmt)
        deleted_da = result.scalar_one_or_none()
        assert deleted_da is None

    async def test_model_field_optional(self, session):
        """model field is optional (nullable)."""
        conv = await self._create_conversation(
            session, external_user_id="user_model_null", conversation_key="model_null_key"
        )

        message = Message(
            conversation_id=conv.id,
            direction="inbound",
            text="No model",
            message_id="msg_model_null",
            prompt_version="v1",
            model=None,
        )
        session.add(message)
        await session.commit()

        assert message.model is None
