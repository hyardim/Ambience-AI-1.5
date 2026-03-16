"""Add session_version to users for token invalidation."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260316_0003"
down_revision: str = "20260316_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("users", "session_version", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "session_version")
