from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.db.session import engine
from src.db.base import Base
import src.db.models  # noqa: F401 — ensures all models are registered before create_all

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ambience AI", version="1.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.api import auth, chats, specialist  # noqa: E402

app.include_router(auth.router,       prefix="/auth",       tags=["Auth"])
app.include_router(chats.router,      prefix="/chats",      tags=["Chats"])
app.include_router(specialist.router, prefix="/specialist",  tags=["Specialist"])


@app.get("/")
def read_root():
    return {"status": "Ambience Backend Running"}


@app.get("/health")
def health():
    return {"status": "healthy", "system": "Ambience-AI-1.5"}
