"""Add user_id_by_app to zalo_users table."""
from alembic import op

revision = "007"
down_revision = "b7de17372549"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("zalo_users", op.Column("user_id_by_app", op.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("zalo_users", "user_id_by_app")
