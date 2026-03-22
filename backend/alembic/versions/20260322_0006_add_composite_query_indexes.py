"""Add composite indexes for common backend query patterns."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260322_0006"
down_revision: str = "20260321_0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _is_postgres() -> bool:
    return op.get_context().dialect.name == "postgresql"


def _create_index(name: str, table: str, columns: list[str]) -> None:
    if _is_postgres():
        # Avoid long table write locks in production by creating indexes concurrently.
        with op.get_context().autocommit_block():
            op.create_index(
                name,
                table,
                columns,
                postgresql_concurrently=True,
            )
        return
    op.create_index(name, table, columns)


def _drop_index(name: str, table: str) -> None:
    if _is_postgres():
        with op.get_context().autocommit_block():
            op.drop_index(
                name,
                table_name=table,
                postgresql_concurrently=True,
            )
        return
    op.drop_index(name, table_name=table)


def upgrade() -> None:
    # users: admin role filters and active-users-by-role stats
    _create_index("ix_users_role", "users", ["role"])
    _create_index("ix_users_is_active", "users", ["is_active"])
    _create_index("ix_users_is_active_role", "users", ["is_active", "role"])

    # chats: user list + archived filter + created_at ordering
    _create_index(
        "ix_chats_user_created_at",
        "chats",
        ["user_id", "created_at"],
    )
    # chats: admin/specialist status views sorted by created_at
    _create_index(
        "ix_chats_status_created_at",
        "chats",
        ["status", "created_at"],
    )
    _create_index(
        "ix_chats_user_archived_created_at",
        "chats",
        ["user_id", "is_archived", "created_at"],
    )
    # chats: specialist queue (submitted + specialty), ordered by created_at
    _create_index(
        "ix_chats_status_specialty_created_at",
        "chats",
        ["status", "specialty", "created_at"],
    )
    # chats: assigned/reviewing list for specialist, ordered by assigned_at
    _create_index(
        "ix_chats_specialist_status_assigned_at",
        "chats",
        ["specialist_id", "status", "assigned_at"],
    )

    # messages: per-chat timeline reads and stream reconstruction
    _create_index(
        "ix_messages_chat_created_at",
        "messages",
        ["chat_id", "created_at"],
    )
    # messages: specialist review lookup (latest AI unreviewed message)
    _create_index(
        "ix_messages_chat_sender_review_created_at",
        "messages",
        ["chat_id", "sender", "review_status", "created_at"],
    )
    # messages: checks for active AI generation in a chat
    _create_index(
        "ix_messages_chat_sender_generating",
        "messages",
        ["chat_id", "sender", "is_generating"],
    )

    # notifications: unread/read listing and unread counts per user
    _create_index(
        "ix_notifications_user_created_at",
        "notifications",
        ["user_id", "created_at"],
    )
    _create_index(
        "ix_notifications_user_read_created_at",
        "notifications",
        ["user_id", "is_read", "created_at"],
    )

    # auth tokens: invalidate active tokens for user efficiently
    _create_index(
        "ix_password_reset_tokens_user_used_expires",
        "password_reset_tokens",
        ["user_id", "used_at", "expires_at"],
    )
    _create_index(
        "ix_email_verification_tokens_user_used_expires",
        "email_verification_tokens",
        ["user_id", "used_at", "expires_at"],
    )

    # audit logs: admin filtering by user/action with timestamp sorting
    _create_index(
        "ix_audit_logs_user_timestamp",
        "audit_logs",
        ["user_id", "timestamp"],
    )
    _create_index(
        "ix_audit_logs_action_timestamp",
        "audit_logs",
        ["action", "timestamp"],
    )


def downgrade() -> None:
    _drop_index(
        "ix_email_verification_tokens_user_used_expires",
        "email_verification_tokens",
    )
    _drop_index(
        "ix_password_reset_tokens_user_used_expires",
        "password_reset_tokens",
    )
    _drop_index("ix_notifications_user_created_at", "notifications")
    _drop_index("ix_messages_chat_sender_generating", "messages")
    _drop_index("ix_audit_logs_action_timestamp", "audit_logs")
    _drop_index("ix_audit_logs_user_timestamp", "audit_logs")
    _drop_index("ix_notifications_user_read_created_at", "notifications")
    _drop_index("ix_messages_chat_sender_review_created_at", "messages")
    _drop_index("ix_messages_chat_created_at", "messages")
    _drop_index("ix_chats_specialist_status_assigned_at", "chats")
    _drop_index("ix_chats_status_specialty_created_at", "chats")
    _drop_index("ix_chats_status_created_at", "chats")
    _drop_index("ix_chats_user_created_at", "chats")
    _drop_index("ix_chats_user_archived_created_at", "chats")
    _drop_index("ix_users_is_active_role", "users")
    _drop_index("ix_users_is_active", "users")
    _drop_index("ix_users_role", "users")
