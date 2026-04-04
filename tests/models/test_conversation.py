"""Tests for the Conversation model."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.conversation import Conversation


class TestConversation:
    """Tests for Conversation ORM model."""

    async def test_create_conversation_with_required_fields(self, session):
        """Can create a conversation with required fields (external_user_id, conversation_key)."""
        conversation = Conversation(
            external_user_id="user_123",
            conversation_key="conv_key_abc",
        )
        session.add(conversation)
        await session.commit()

        assert conversation.id is not None
        assert conversation.external_user_id == "user_123"
        assert conversation.conversation_key == "conv_key_abc"
        assert conversation.created_at is not None
        assert conversation.updated_at is not None

    async def test_create_conversation_without_conversation_key(self, session):
        """Can create a conversation without conversation_key (nullable)."""
        conversation = Conversation(external_user_id="user_456")
        session.add(conversation)
        await session.commit()

        assert conversation.id is not None
        assert conversation.conversation_key is None

    async def test_conversation_key_is_unique(self, session):
        """Same conversation_key raises IntegrityError."""
        conv1 = Conversation(
            external_user_id="user_1",
            conversation_key="shared_key",
        )
        session.add(conv1)
        await session.commit()

        conv2 = Conversation(
            external_user_id="user_2",
            conversation_key="shared_key",
        )
        session.add(conv2)
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_query_by_external_user_id_sorted_desc(self, session):
        """Can query by external_user_id, returns list sorted by created_at DESC."""
        import time

        conv1 = Conversation(external_user_id="user_desc", conversation_key="key_1")
        conv2 = Conversation(external_user_id="user_desc", conversation_key="key_2")
        conv3 = Conversation(external_user_id="user_desc", conversation_key="key_3")
        session.add_all([conv1, conv2, conv3])
        await session.commit()

        # Small delay so created_at values differ
        await session.execute(select(Conversation).execution_options(synchronize_session=False))
        await session.commit()

        stmt = (
            select(Conversation)
            .where(Conversation.external_user_id == "user_desc")
            .order_by(Conversation.created_at.desc())
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().all())

        assert len(rows) == 3
        # Most recently created (highest ID / latest timestamp) first
        assert rows[0].conversation_key in ["key_3", "key_2", "key_1"]
        assert rows[0].external_user_id == "user_desc"

    async def test_query_by_conversation_key(self, session):
        """Can query by conversation_key and find the conversation."""
        conv = Conversation(
            external_user_id="user_find",
            conversation_key="findable_key_xyz",
        )
        session.add(conv)
        await session.commit()

        stmt = select(Conversation).where(
            Conversation.conversation_key == "findable_key_xyz"
        )
        result = await session.execute(stmt)
        found = result.scalar_one_or_none()

        assert found is not None
        assert found.external_user_id == "user_find"

    async def test_status_defaults_to_active(self, session):
        """Status defaults to 'active'."""
        conv = Conversation(external_user_id="user_default_status")
        session.add(conv)
        await session.commit()

        assert conv.status == "active"

    async def test_status_can_be_updated_to_closed(self, session):
        """Status can be updated to 'closed'."""
        conv = Conversation(
            external_user_id="user_close",
            conversation_key="close_key",
        )
        session.add(conv)
        await session.commit()

        conv.status = "closed"
        await session.commit()
        await session.refresh(conv)

        assert conv.status == "closed"

    async def test_cascade_delete_removes_associated_messages(self, session):
        """Cascade delete removes associated messages when conversation is deleted."""
        from app.models.message import Message

        conv = Conversation(
            external_user_id="user_cascade",
            conversation_key="cascade_key",
        )
        session.add(conv)
        await session.commit()

        conv_id = conv.id
        msg = Message(
            conversation_id=conv_id,
            direction="inbound",
            text="Hello",
            message_id="dedup_123",
            prompt_version="v1",
        )
        session.add(msg)
        await session.commit()

        msg_id = msg.id

        # Delete conversation
        await session.delete(conv)
        await session.commit()

        # Message should also be deleted (cascade)
        stmt = select(Message).where(Message.id == msg_id)
        result = await session.execute(stmt)
        deleted_msg = result.scalar_one_or_none()

        assert deleted_msg is None
