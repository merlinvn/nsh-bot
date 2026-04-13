"""Zalo user ORM model."""
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ZaloUser(Base, UUIDMixin, TimestampMixin):
    """Stores Zalo user profile information fetched from the Zalo API."""

    __tablename__ = "zalo_users"

    user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    user_alias: Mapped[str | None] = mapped_column(String(256), nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_last_interaction_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    user_is_follower: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    shared_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tags_and_notes_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    user_external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id_by_app: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_sensitive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
