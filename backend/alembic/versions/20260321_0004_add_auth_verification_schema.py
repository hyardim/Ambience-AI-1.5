"""Add auth verification columns and token tables.

This migration aligns the persisted schema with the current auth models by:
- adding users.email_verified and users.email_verified_at
- creating password_reset_tokens and email_verification_tokens tables
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260321_0004"
down_revision: str = "20260316_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(), nullable=True))
    op.alter_column("users", "email_verified", server_default=None)

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_password_reset_tokens_id", "password_reset_tokens", ["id"])
    op.create_index(
        "ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"]
    )
    op.create_index(
        "ix_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
    )
    op.create_index(
        "ix_password_reset_tokens_expires_at",
        "password_reset_tokens",
        ["expires_at"],
    )
    op.create_index("ix_password_reset_tokens_used_at", "password_reset_tokens", ["used_at"])
    op.create_index(
        "ix_password_reset_tokens_created_at",
        "password_reset_tokens",
        ["created_at"],
    )
    op.create_index(
        "ix_password_reset_tokens_user_created",
        "password_reset_tokens",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_password_reset_tokens_expiry_used",
        "password_reset_tokens",
        ["expires_at", "used_at"],
    )

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_email_verification_tokens_id",
        "email_verification_tokens",
        ["id"],
    )
    op.create_index(
        "ix_email_verification_tokens_user_id",
        "email_verification_tokens",
        ["user_id"],
    )
    op.create_index(
        "ix_email_verification_tokens_token_hash",
        "email_verification_tokens",
        ["token_hash"],
    )
    op.create_index(
        "ix_email_verification_tokens_expires_at",
        "email_verification_tokens",
        ["expires_at"],
    )
    op.create_index(
        "ix_email_verification_tokens_used_at",
        "email_verification_tokens",
        ["used_at"],
    )
    op.create_index(
        "ix_email_verification_tokens_created_at",
        "email_verification_tokens",
        ["created_at"],
    )
    op.create_index(
        "ix_email_verification_tokens_user_created",
        "email_verification_tokens",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_email_verification_tokens_expiry_used",
        "email_verification_tokens",
        ["expires_at", "used_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_verification_tokens_expiry_used",
        table_name="email_verification_tokens",
    )
    op.drop_index(
        "ix_email_verification_tokens_user_created",
        table_name="email_verification_tokens",
    )
    op.drop_index(
        "ix_email_verification_tokens_created_at",
        table_name="email_verification_tokens",
    )
    op.drop_index(
        "ix_email_verification_tokens_used_at",
        table_name="email_verification_tokens",
    )
    op.drop_index(
        "ix_email_verification_tokens_expires_at",
        table_name="email_verification_tokens",
    )
    op.drop_index(
        "ix_email_verification_tokens_token_hash",
        table_name="email_verification_tokens",
    )
    op.drop_index(
        "ix_email_verification_tokens_user_id",
        table_name="email_verification_tokens",
    )
    op.drop_index(
        "ix_email_verification_tokens_id",
        table_name="email_verification_tokens",
    )
    op.drop_table("email_verification_tokens")

    op.drop_index(
        "ix_password_reset_tokens_expiry_used",
        table_name="password_reset_tokens",
    )
    op.drop_index(
        "ix_password_reset_tokens_user_created",
        table_name="password_reset_tokens",
    )
    op.drop_index(
        "ix_password_reset_tokens_created_at",
        table_name="password_reset_tokens",
    )
    op.drop_index("ix_password_reset_tokens_used_at", table_name="password_reset_tokens")
    op.drop_index(
        "ix_password_reset_tokens_expires_at",
        table_name="password_reset_tokens",
    )
    op.drop_index(
        "ix_password_reset_tokens_token_hash",
        table_name="password_reset_tokens",
    )
    op.drop_index(
        "ix_password_reset_tokens_user_id",
        table_name="password_reset_tokens",
    )
    op.drop_index("ix_password_reset_tokens_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")