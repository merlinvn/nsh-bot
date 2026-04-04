"""Conversation ORM model."""
from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Conversation(Base, UUIDMixin, TimestampMixin):
    """Stores conversation sessions with a Zalo user."""

    __tablename__ = "conversations"

    external_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conversation_key: Mapped[str | None] = mapped_column(String(256), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    __table_args__ = (
        Index("ix_conversations_external_user_id", "external_user_id", "created_at"),
        Index("ix_conversations_conversation_key", "conversation_key"),
        Index("ix_conversations_status", "status"),
    )


from app.models.message import Message  # noqa: E402, F401
