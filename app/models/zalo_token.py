"""Zalo OAuth token storage model."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ZaloToken(Base):
    """Stores Zalo OAuth access and refresh tokens."""

    __tablename__ = "zalo_tokens"

    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    access_token: Mapped[str] = mapped_column(String(1024), nullable=False)
    refresh_token: Mapped[str] = mapped_column(String(512), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # PKCE code_verifier and code_challenge for OAuth flow
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=True)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
