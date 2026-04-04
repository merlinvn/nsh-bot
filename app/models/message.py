"""Message ORM model."""
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Message(Base, UUIDMixin, TimestampMixin):
    """Stores individual messages within a conversation."""

    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        "ToolCall",
        back_populates="message",
        cascade="all, delete-orphan",
    )
    delivery_attempts: Mapped[list["DeliveryAttempt"]] = relationship(
        "DeliveryAttempt",
        back_populates="message",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_message_id", "message_id"),
    )


from app.models.conversation import Conversation  # noqa: E402, F401
from app.models.tool_call import ToolCall  # noqa: E402, F401
from app.models.delivery_attempt import DeliveryAttempt  # noqa: E402, F401
