"""ToolCall ORM model."""
from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ToolCall(Base, UUIDMixin, TimestampMixin):
    """Stores tool calls made during message processing."""

    __tablename__ = "tool_calls"

    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    success: Mapped[bool] = mapped_column(nullable=False)
    error: Mapped[str | None] = mapped_column(nullable=True)
    latency_ms: Mapped[int] = mapped_column(nullable=False)

    message: Mapped["Message"] = relationship("Message", back_populates="tool_calls")

    __table_args__ = (Index("ix_tool_calls_message_id", "message_id"),)


from app.models.message import Message  # noqa: E402, F401
