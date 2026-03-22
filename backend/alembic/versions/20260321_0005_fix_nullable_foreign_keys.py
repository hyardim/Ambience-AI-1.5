"""Fix nullable foreign key columns to match ORM model constraints.

The initial migration (0001) created several FK columns as nullable=True,
but the ORM models declare them as nullable=False.  This migration aligns
the database schema with the models to prevent orphan rows and enforce
referential integrity at the database level.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260321_0005"
down_revision: str = "20260321_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # chats.user_id: nullable=True -> nullable=False
    op.alter_column(
        "chats",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # messages.chat_id: nullable=True -> nullable=False
    op.alter_column(
        "messages",
        "chat_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # file_attachments.chat_id: nullable=True -> nullable=False
    op.alter_column(
        "file_attachments",
        "chat_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # file_attachments.uploader_id: nullable=True -> nullable=False
    op.alter_column(
        "file_attachments",
        "uploader_id",
        existing_type=sa.Integer(),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "file_attachments",
        "uploader_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "file_attachments",
        "chat_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "messages",
        "chat_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "chats",
        "user_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
