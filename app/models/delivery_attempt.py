"""DeliveryAttempt ORM model."""
from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class DeliveryAttempt(Base, UUIDMixin, TimestampMixin):
    """Stores delivery attempt records for outbound messages."""

    __tablename__ = "delivery_attempts"

    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(nullable=True)

    message: Mapped["Message"] = relationship("Message", back_populates="delivery_attempts")

    __table_args__ = (
        Index("ix_delivery_attempts_message_id", "message_id"),
        Index("ix_delivery_attempts_status", "status"),
    )


from app.models.message import Message  # noqa: E402, F401
