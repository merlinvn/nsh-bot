"""BenchmarkResult and BenchmarkItem ORM models."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class BenchmarkResult(Base):
    """Stores benchmark run results."""

    __tablename__ = "benchmark_results"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    iterations: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["BenchmarkItem"]] = relationship(
        "BenchmarkItem", back_populates="benchmark", cascade="all, delete-orphan"
    )


class BenchmarkItem(Base):
    """Stores individual model benchmark results within a benchmark run."""

    __tablename__ = "benchmark_items"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    benchmark_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.benchmark_results.id", ondelete="CASCADE"), nullable=False
    )
    model_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    avg_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    benchmark: Mapped["BenchmarkResult"] = relationship("BenchmarkResult", back_populates="items")
