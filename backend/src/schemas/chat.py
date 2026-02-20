from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


# --- Message Schemas ---
class MessageBase(BaseModel):
    role: str  # "user" or "assistant"
    content: str  # "What is diabetes?"


class MessageCreate(MessageBase):
    pass


class MessageResponse(MessageBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Chat Schemas ---
class ChatBase(BaseModel):
    title: Optional[str] = None


class ChatCreate(ChatBase):
    pass


class ChatResponse(ChatBase):
    id: int
    user_id: int
    created_at: datetime
    messages: List[MessageResponse] = []

    class Config:
        from_attributes = True
