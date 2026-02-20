from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from src.api import rag, auth
from src.core import security
import os

from src.db.base import Base
from src.db.session import engine
from src.db.models import User
from src.db.session import SessionLocal
from src.api import auth, chats

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
            "role": "gp",
            "specialty": None,
        },
        {
            "email": "specialist@example.com",
            "password": "password123",
            "full_name": "Dr. Specialist User",
            "role": "specialist",
            "specialty": "neurology",
        },
        {
            "email": "admin@example.com",
            "password": "password123",
            "full_name": "System Admin",
            "role": "admin",
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

# Initialize the application
app = FastAPI(
    title="Ambience-AI-1.5 API",
    description="Clinical RAG Backend for Neurology & Rheumatology Support",
    version="1.5.0",
)

# CORS: Allow your frontend (running on port 3000) to talk to this backend
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the Authentication Router (we will fill this file next)
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(rag.router, tags=["RAG"])
app.include_router(
    chats.router, prefix="/chats", tags=["chats"]
)  # <--- ✅ ADD THIS LINE


@app.get("/health")
def health_check():
    """Confirms the backend is running."""
    return {"status": "healthy", "system": "Ambience-AI-1.5"}
