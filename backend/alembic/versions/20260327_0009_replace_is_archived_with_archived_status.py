"""Replace is_archived boolean with ChatStatus.ARCHIVED.

Migrates existing archived chats (is_archived=True) to status='archived',
then drops the is_archived column and its composite index.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260327_0009"
down_revision: str = "20260323_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Migrate any rows that were soft-deleted via is_archived to use the
    # ARCHIVED status value instead.
    op.execute("UPDATE chats SET status = 'archived' WHERE is_archived = true")

    op.drop_index("ix_chats_user_archived_created_at", table_name="chats")
    op.drop_column("chats", "is_archived")


def downgrade() -> None:
    op.add_column(
        "chats",
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_chats_user_archived_created_at",
        "chats",
        ["user_id", "is_archived", "created_at"],
    )
    op.execute("UPDATE chats SET is_archived = true WHERE status = 'archived'")
