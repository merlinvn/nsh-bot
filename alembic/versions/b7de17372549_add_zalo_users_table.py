"""add zalo_users table

Revision ID: 007
Revises: 006
Create Date: 2026-04-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zalo_users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(256), nullable=True),
        sa.Column("user_alias", sa.String(256), nullable=True),
        sa.Column("avatar", sa.Text(), nullable=True),
        sa.Column("user_last_interaction_date", sa.String(16), nullable=True),
        sa.Column("user_is_follower", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("shared_info", sa.JSON(), nullable=True),
        sa.Column("tags_and_notes_info", sa.JSON(), nullable=True),
        sa.Column("user_external_id", sa.String(64), nullable=True),
        sa.Column("is_sensitive", sa.Boolean(), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_zalo_users_user_id", "zalo_users", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_zalo_users_user_id", table_name="zalo_users")
    op.drop_table("zalo_users")
