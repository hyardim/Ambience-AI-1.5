from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from src.core import security
import os

from src.db.base import Base
from src.db.session import engine
from src.db.models import User, UserRole
from src.db.session import SessionLocal
import src.db.models  # noqa: F401 — ensures all models are registered before create_all

Base.metadata.create_all(bind=engine)


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
    """Re-create notifications.chat_id FK with ON DELETE SET NULL.

    The original constraint (created by create_all before this fix) has no
    ondelete behaviour, which causes a FK violation when a chat is deleted
    while notifications referencing it still exist.  Running this at startup
    is idempotent — DROP IF EXISTS means a clean DB is unaffected.
    """
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
    """Add newer message columns for older databases."""
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
    """Add newer chat metadata columns for older databases."""
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


def ensure_default_users() -> None:
    if os.getenv("AUTH_BOOTSTRAP_DEMO_USERS", "true").lower() != "true":
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
                    hashed_password=security.get_password_hash(
                        item["password"]),
                    full_name=item["full_name"],
                    role=item["role"],
                    specialty=item["specialty"],
                )
            )
        db.commit()
    finally:
        db.close()


def ensure_chat_archive_column() -> None:
    """Add is_archived column to chats table if missing."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE chats "
                "ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )


def ensure_enum_columns_lowercase() -> None:
    """Migrate any uppercase enum values to lowercase and convert native enum
    columns to plain VARCHAR.  Handles users.role, chats.status and
    notifications.type.
    """
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


ensure_auth_columns()
ensure_notification_fk()
ensure_message_columns()
ensure_chat_archive_column()
ensure_chat_columns()
ensure_enum_columns_lowercase()
ensure_default_users()

app = FastAPI(
    title="Ambience-AI-1.5 API",
    description="Clinical RAG Backend for Neurology & Rheumatology Support",
    version="1.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.api import auth, chats, specialist, rag, notifications, admin  # noqa: E402

app.include_router(auth.router,          prefix="/auth",
                   tags=["Auth"])
app.include_router(chats.router,         prefix="/chats",
                   tags=["Chats"])
app.include_router(specialist.router,
                   prefix="/specialist",    tags=["Specialist"])
app.include_router(notifications.router,
                   prefix="/notifications", tags=["Notifications"])
app.include_router(admin.router,         prefix="/admin",
                   tags=["Admin"])
app.include_router(rag.router,           tags=["RAG"])


@app.get("/")
def read_root():
    return {"status": "Ambience Backend Running"}


@app.get("/health")
def health():
    return {"status": "healthy", "system": "Ambience-AI-1.5"}
