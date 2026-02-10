from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.db.session import engine
from src.db.base import Base
# ✅ CRITICAL: We must import models so the DB knows what to build
import src.db.models 

# ✅ CRITICAL: This command actually creates the 'users' table you just dropped
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ambience AI", version="1.5.0")

# Enable CORS (Allows Frontend to talk to Backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import Routes
from src.api import auth, chats

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(chats.router, prefix="/chats", tags=["Chats"])

@app.get("/")
def read_root():
    return {"status": "Ambience Backend Running"}