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
                    hashed_password=security.get_password_hash(item["password"]),
                    full_name=item["full_name"],
                    role=item["role"],
                    specialty=item["specialty"],
                )
            )
        db.commit()
    finally:
        db.close()


ensure_auth_columns()
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

app.include_router(auth.router,          prefix="/auth",          tags=["Auth"])
app.include_router(chats.router,         prefix="/chats",         tags=["Chats"])
app.include_router(specialist.router,    prefix="/specialist",    tags=["Specialist"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
app.include_router(admin.router,         prefix="/admin",         tags=["Admin"])
app.include_router(rag.router,           tags=["RAG"])


@app.get("/")
def read_root():
    return {"status": "Ambience Backend Running"}


@app.get("/health")
def health():
    return {"status": "healthy", "system": "Ambience-AI-1.5"}
