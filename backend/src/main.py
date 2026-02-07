from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api import rag, auth
from src.core import security

from src.db.base import Base
from src.db.session import engine
from src.db import models  
from src.api import auth, chats
Base.metadata.create_all(bind=engine)

# Initialize the application
app = FastAPI(
    title="Ambience-AI-1.5 API",
    description="Clinical RAG Backend for Neurology & Rheumatology Support",
    version="1.5.0"
)

# CORS: Allow your frontend (running on port 3000) to talk to this backend
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
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
app.include_router(chats.router, prefix="/chats", tags=["chats"]) # <--- ✅ ADD THIS LINE

@app.get("/health")
def health_check():
    """Confirms the backend is running."""
    return {"status": "healthy", "system": "Ambience-AI-1.5"}