"""Tests for the DeliveryAttempt model."""
import pytest
from sqlalchemy import select

from app.models.conversation import Conversation
from app.models.delivery_attempt import DeliveryAttempt
from app.models.message import Message


class TestDeliveryAttempt:
    """Tests for DeliveryAttempt ORM model."""

    async def _create_message(self, session, **kwargs):
        """Helper to create a conversation and message."""
        conv = Conversation(
            external_user_id=kwargs.get("external_user_id", "user_da_test"),
            conversation_key=kwargs.get("conversation_key", "da_conv_key"),
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)

        msg = Message(
            conversation_id=conv.id,
            direction=kwargs.get("direction", "outbound"),
            text=kwargs.get("text", "Test message for delivery attempt"),
            message_id=kwargs.get("message_id", "da_msg_001"),
            prompt_version=kwargs.get("prompt_version", "v1"),
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return msg

    async def test_create_delivery_attempt_linked_to_message(self, session):
        """Can create delivery_attempt linked to message via FK."""
        msg = await self._create_message(session)

        attempt = DeliveryAttempt(
            message_id=msg.id,
            attempt_no=1,
            status="pending",
        )
        session.add(attempt)
        await session.commit()

        assert attempt.id is not None
        assert attempt.message_id == msg.id
        assert attempt.attempt_no == 1

    async def test_attempt_no_increments_correctly(self, session):
        """attempt_no increments correctly across attempts for the same message."""
        msg = await self._create_message(session, message_id="da_msg_increment")

        attempts = [
            DeliveryAttempt(message_id=msg.id, attempt_no=1, status="pending"),
            DeliveryAttempt(message_id=msg.id, attempt_no=2, status="failed"),
            DeliveryAttempt(message_id=msg.id, attempt_no=3, status="success"),
        ]
        session.add_all(attempts)
        await session.commit()

        stmt = (
            select(DeliveryAttempt)
            .where(DeliveryAttempt.message_id == msg.id)
            .order_by(DeliveryAttempt.attempt_no)
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().all())

        assert len(rows) == 3
        assert [a.attempt_no for a in rows] == [1, 2, 3]

    async def test_status_pending_success_failed(self, session):
        """status accepts 'pending', 'success', and 'failed' values."""
        msg = await self._create_message(session, message_id="da_msg_status")

        pending = DeliveryAttempt(
            message_id=msg.id, attempt_no=1, status="pending"
        )
        success = DeliveryAttempt(
            message_id=msg.id, attempt_no=2, status="success"
        )
        failed = DeliveryAttempt(
            message_id=msg.id, attempt_no=3, status="failed"
        )
        session.add_all([pending, success, failed])
        await session.commit()

        assert pending.status == "pending"
        assert success.status == "success"
        assert failed.status == "failed"

    async def test_response_stored_as_jsonb(self, session):
        """response is stored as JSONB (dict)."""
        msg = await self._create_message(session, message_id="da_msg_response")

        response_data = {
            "zalo_api_response": {
                "success": True,
                "message_id": "zalo_msg_123",
                "timestamp": 1710000000,
            }
        }
        attempt = DeliveryAttempt(
            message_id=msg.id,
            attempt_no=1,
            status="success",
            response=response_data,
        )
        session.add(attempt)
        await session.commit()

        await session.refresh(attempt)
        assert attempt.response == response_data
        assert attempt.response["zalo_api_response"]["message_id"] == "zalo_msg_123"

    async def test_error_stored_as_text(self, session):
        """error field is stored as text."""
        msg = await self._create_message(session, message_id="da_msg_error")

        attempt = DeliveryAttempt(
            message_id=msg.id,
            attempt_no=1,
            status="failed",
            error="HTTP 503: Service temporarily unavailable",
        )
        session.add(attempt)
        await session.commit()

        await session.refresh(attempt)
        assert attempt.error == "HTTP 503: Service temporarily unavailable"

    async def test_error_can_be_null(self, session):
        """error field can be null (successful delivery may have no error)."""
        msg = await self._create_message(session, message_id="da_msg_no_error")

        attempt = DeliveryAttempt(
            message_id=msg.id,
            attempt_no=1,
            status="success",
            error=None,
        )
        session.add(attempt)
        await session.commit()

        await session.refresh(attempt)
        assert attempt.error is None

    async def test_response_can_be_null(self, session):
        """response field can be null."""
        msg = await self._create_message(session, message_id="da_msg_no_response")

        attempt = DeliveryAttempt(
            message_id=msg.id,
            attempt_no=1,
            status="pending",
            response=None,
        )
        session.add(attempt)
        await session.commit()

        await session.refresh(attempt)
        assert attempt.response is None
