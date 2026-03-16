from sqlalchemy import text
from src.core import security
from src.core.config import settings
from src.db.base import Base
from src.db.models import User, UserRole
from src.db.session import SessionLocal, engine


def ensure_auth_columns() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR NOT NULL DEFAULT 'gp'"
            )
        )
        connection.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS specialty VARCHAR")
        )


def ensure_notification_fk() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE notifications "
                "DROP CONSTRAINT IF EXISTS notifications_chat_id_fkey"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE notifications "
                "ADD CONSTRAINT notifications_chat_id_fkey "
                "FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE SET NULL"
            )
        )


def ensure_message_columns() -> None:
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS role VARCHAR")
        )
        connection.execute(
            text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender VARCHAR")
        )
        connection.execute(
            text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS citations JSONB")
        )
        connection.execute(
            text(
                "ALTER TABLE messages "
                "ADD COLUMN IF NOT EXISTS is_generating BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        connection.execute(
            text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS review_status VARCHAR")
        )
        connection.execute(
            text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS review_feedback TEXT")
        )
        connection.execute(
            text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP")
        )


def ensure_chat_columns() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE chats "
                "ADD COLUMN IF NOT EXISTS status VARCHAR NOT NULL DEFAULT 'open'"
            )
        )
        connection.execute(
            text("ALTER TABLE chats ADD COLUMN IF NOT EXISTS specialty VARCHAR")
        )
        connection.execute(
            text("ALTER TABLE chats ADD COLUMN IF NOT EXISTS severity VARCHAR")
        )
        connection.execute(
            text("ALTER TABLE chats ADD COLUMN IF NOT EXISTS patient_context JSONB")
        )
        connection.execute(
            text("ALTER TABLE chats ADD COLUMN IF NOT EXISTS specialist_id INTEGER")
        )
        connection.execute(
            text("ALTER TABLE chats ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP")
        )
        connection.execute(
            text("ALTER TABLE chats ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP")
        )
        connection.execute(
            text("ALTER TABLE chats ADD COLUMN IF NOT EXISTS review_feedback TEXT")
        )
        connection.execute(
            text(
                "ALTER TABLE chats "
                "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW()"
            )
        )


def ensure_chat_archive_column() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE chats "
                "ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )


def ensure_enum_columns_lowercase() -> None:
    with engine.begin() as connection:
        for table, column in [
            ("users", "role"),
            ("chats", "status"),
            ("notifications", "type"),
        ]:
            connection.execute(
                text(
                    f"ALTER TABLE {table} "
                    f"ALTER COLUMN {column} TYPE VARCHAR USING {column}::TEXT"
                )
            )
            connection.execute(
                text(
                    f"UPDATE {table} SET {column} = LOWER({column}) "
                    f"WHERE {column} != LOWER({column})"
                )
            )


def ensure_default_users() -> None:
    if not settings.AUTH_BOOTSTRAP_DEMO_USERS:
        return

    defaults = [
        {
            "email": "gp@example.com",
            "password": "password123",
            "full_name": "Dr. GP User",
            "role": UserRole.GP,
            "specialty": None,
        },
        {
            "email": "specialist@example.com",
            "password": "password123",
            "full_name": "Dr. Specialist User",
            "role": UserRole.SPECIALIST,
            "specialty": "neurology",
        },
        {
            "email": "admin@example.com",
            "password": "password123",
            "full_name": "System Admin",
            "role": UserRole.ADMIN,
            "specialty": None,
        },
    ]

    db = SessionLocal()
    try:
        for item in defaults:
            exists = db.query(User).filter(User.email == item["email"]).first()
            if exists:
                continue
            db.add(
                User(
                    email=item["email"],
                    hashed_password=security.get_password_hash(item["password"]),
                    full_name=item["full_name"],
                    role=item["role"],
                    specialty=item["specialty"],
                )
            )
        db.commit()
    finally:
        db.close()


def prepare_database() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_auth_columns()
    ensure_notification_fk()
    ensure_message_columns()
    ensure_chat_archive_column()
    ensure_chat_columns()
    ensure_enum_columns_lowercase()
    ensure_default_users()
