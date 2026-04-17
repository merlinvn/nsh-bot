"""Add user_id_by_app to zalo_users table."""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("zalo_users", sa.Column("user_id_by_app", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("zalo_users", "user_id_by_app")
