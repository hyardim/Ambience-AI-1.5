"""Add is_error flag to messages table.

Allows failed AI generation messages to be excluded from conversation
history so they do not corrupt subsequent LLM prompts.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260323_0008"
down_revision: str = "20260322_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "is_error",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("messages", "is_error")
