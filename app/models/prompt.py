"""Prompt ORM model."""
from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Prompt(Base, UUIDMixin, TimestampMixin):
    """Stores prompt templates with versioning support."""

    __tablename__ = "prompts"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    versions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    active_version: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (Index("ix_prompts_name", "name"),)
