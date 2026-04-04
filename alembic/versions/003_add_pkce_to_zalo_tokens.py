"""add PKCE columns to zalo_tokens

Revision ID: 003
Revises: 002
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("zalo_tokens", sa.Column("code_verifier", sa.String(128), nullable=True))
    op.add_column("zalo_tokens", sa.Column("code_challenge", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("zalo_tokens", "code_challenge")
    op.drop_column("zalo_tokens", "code_verifier")