"""Enforce non-null defaults for core backend columns.

This migration aligns persisted nullability with ORM model constraints for
columns that should always have values at runtime.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260322_0007"
down_revision: str = "20260322_0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Backfill legacy nullable rows before tightening constraints.
    op.execute("UPDATE users SET role = 'gp' WHERE role IS NULL")
    op.execute("UPDATE users SET is_active = TRUE WHERE is_active IS NULL")

    op.execute("UPDATE chats SET title = 'New Chat' WHERE title IS NULL")
    op.execute("UPDATE chats SET status = 'open' WHERE status IS NULL")

    op.execute("UPDATE messages SET sender = 'user' WHERE sender IS NULL")
    op.execute("UPDATE messages SET is_generating = FALSE WHERE is_generating IS NULL")

    op.execute("UPDATE notifications SET is_read = FALSE WHERE is_read IS NULL")

    op.alter_column("users", "role", existing_type=sa.String(), nullable=False)
    op.alter_column("users", "is_active", existing_type=sa.Boolean(), nullable=False)

    op.alter_column("chats", "title", existing_type=sa.String(), nullable=False)
    op.alter_column("chats", "status", existing_type=sa.String(), nullable=False)

    op.alter_column("messages", "sender", existing_type=sa.String(), nullable=False)
    op.alter_column(
        "messages",
        "is_generating",
        existing_type=sa.Boolean(),
        nullable=False,
        existing_server_default=sa.text("false"),
    )

    op.alter_column(
        "notifications",
        "is_read",
        existing_type=sa.Boolean(),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column("notifications", "is_read", existing_type=sa.Boolean(), nullable=True)

    op.alter_column(
        "messages",
        "is_generating",
        existing_type=sa.Boolean(),
        nullable=True,
        existing_server_default=sa.text("false"),
    )
    op.alter_column("messages", "sender", existing_type=sa.String(), nullable=True)

    op.alter_column("chats", "status", existing_type=sa.String(), nullable=True)
    op.alter_column("chats", "title", existing_type=sa.String(), nullable=True)

    op.alter_column("users", "is_active", existing_type=sa.Boolean(), nullable=True)
    op.alter_column("users", "role", existing_type=sa.String(), nullable=True)
