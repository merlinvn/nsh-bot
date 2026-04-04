"""add zalo tokens

Revision ID: 002
Revises: 001
Create Date: 2026-04-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zalo_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("access_token", sa.String(1024), nullable=False),
        sa.Column("refresh_token", sa.String(512), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )


def downgrade() -> None:
    op.drop_table("zalo_tokens")
