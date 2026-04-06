"""Add admin_user, benchmark_result, benchmark_item tables

Revision ID: 004
Revises: 003
Create Date: 2026-04-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # admin_users table
    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_admin_users_username", "admin_users", ["username"], unique=True)

    # benchmark_results table
    op.create_table(
        "benchmark_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("iterations", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # benchmark_items table
    op.create_table(
        "benchmark_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "benchmark_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("benchmark_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_provider", sa.String(32), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("avg_latency_ms", sa.Float(), nullable=True),
        sa.Column("p95_latency_ms", sa.Float(), nullable=True),
        sa.Column("avg_input_tokens", sa.Integer(), nullable=True),
        sa.Column("avg_output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_cost", sa.Float(), nullable=True),
        sa.Column("raw_results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_benchmark_items_benchmark_id", "benchmark_items", ["benchmark_id"])


def downgrade() -> None:
    op.drop_table("benchmark_items")
    op.drop_table("benchmark_results")
    op.drop_table("admin_users")
