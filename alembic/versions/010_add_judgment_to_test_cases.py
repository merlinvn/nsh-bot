"""Add judgment column to evaluation_test_cases.

Revision ID: 010
Revises: 009
Create Date: 2026-04-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evaluation_test_cases",
        sa.Column("judgment", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_test_cases", "judgment")
