"""backend_schema_baseline

Revision ID: a8d9c6b2f1e4
Revises: 39038320b4c5
Create Date: 2026-03-24 12:05:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a8d9c6b2f1e4"
down_revision: Union[str, None] = "39038320b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Core tables
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR NOT NULL,
            hashed_password VARCHAR NOT NULL,
            full_name VARCHAR,
            role VARCHAR,
            specialty VARCHAR,
            is_active BOOLEAN,
            email_verified BOOLEAN NOT NULL,
            email_verified_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email
        ON users (email)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chats (
            id SERIAL PRIMARY KEY,
            title VARCHAR,
            status VARCHAR,
            specialty VARCHAR,
            severity VARCHAR,
            patient_context JSONB,
            patient_age INTEGER,
            patient_gender VARCHAR,
            patient_notes TEXT,
            is_archived BOOLEAN NOT NULL DEFAULT FALSE,
            specialist_id INTEGER REFERENCES users(id),
            assigned_at TIMESTAMP,
            reviewed_at TIMESTAMP,
            review_feedback TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            user_id INTEGER REFERENCES users(id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            content TEXT,
            role VARCHAR,
            sender VARCHAR,
            created_at TIMESTAMP,
            citations JSONB,
            is_generating BOOLEAN DEFAULT FALSE,
            review_status VARCHAR,
            review_feedback TEXT,
            reviewed_at TIMESTAMP,
            chat_id INTEGER REFERENCES chats(id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            type VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            body VARCHAR,
            chat_id INTEGER REFERENCES chats(id) ON DELETE SET NULL,
            is_read BOOLEAN,
            created_at TIMESTAMP
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS file_attachments (
            id SERIAL PRIMARY KEY,
            filename VARCHAR NOT NULL,
            file_path VARCHAR NOT NULL,
            file_type VARCHAR,
            file_size INTEGER,
            created_at TIMESTAMP,
            chat_id INTEGER REFERENCES chats(id),
            uploader_id INTEGER REFERENCES users(id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            action VARCHAR,
            details VARCHAR,
            timestamp TIMESTAMP
        )
        """
    )

    # Token tables used by auth flows
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash VARCHAR NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_created
        ON password_reset_tokens (user_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_expiry_used
        ON password_reset_tokens (expires_at, used_at)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS email_verification_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash VARCHAR NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_email_verification_tokens_user_created
        ON email_verification_tokens (user_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_email_verification_tokens_expiry_used
        ON email_verification_tokens (expires_at, used_at)
        """
    )


def downgrade() -> None:
    # Keep downgrade non-destructive for baseline/idempotent migration.
    pass
