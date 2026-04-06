"""Add messages error column and analytics indexes

Revision ID: 005
Revises: 004
Create Date: 2026-04-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("error", sa.Text(), nullable=True))
    op.create_index("ix_conversations_created_at", "conversations", ["created_at"], unique=False)
    op.create_index("ix_messages_created_at", "messages", ["created_at"], unique=False)
    op.create_index("ix_messages_direction_created", "messages", ["direction", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_messages_direction_created", table_name="messages")
    op.drop_index("ix_messages_created_at", table_name="messages")
    op.drop_index("ix_conversations_created_at", table_name="conversations")
    op.drop_column("messages", "error")
