"""Add performance indexes on frequently queried columns."""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260316_0002"
down_revision: str = "20260316_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # chats
    op.create_index("ix_chats_user_id", "chats", ["user_id"])
    op.create_index("ix_chats_specialist_id", "chats", ["specialist_id"])
    op.create_index("ix_chats_status", "chats", ["status"])
    op.create_index("ix_chats_specialty", "chats", ["specialty"])
    op.create_index("ix_chats_created_at", "chats", ["created_at"])

    # messages
    op.create_index("ix_messages_chat_id", "messages", ["chat_id"])
    op.create_index("ix_messages_sender", "messages", ["sender"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])

    # audit_logs
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])

    # notifications
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])

    # file_attachments
    op.create_index("ix_file_attachments_chat_id", "file_attachments", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_file_attachments_chat_id", table_name="file_attachments")
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_audit_logs_timestamp", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_index("ix_messages_created_at", table_name="messages")
    op.drop_index("ix_messages_sender", table_name="messages")
    op.drop_index("ix_messages_chat_id", table_name="messages")
    op.drop_index("ix_chats_created_at", table_name="chats")
    op.drop_index("ix_chats_specialty", table_name="chats")
    op.drop_index("ix_chats_status", table_name="chats")
    op.drop_index("ix_chats_specialist_id", table_name="chats")
    op.drop_index("ix_chats_user_id", table_name="chats")
