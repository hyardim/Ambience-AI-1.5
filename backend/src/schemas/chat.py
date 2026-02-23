from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

class MessageBase(BaseModel):
    content: str

class MessageCreate(MessageBase):
    pass

class MessageResponse(BaseModel):
    id: int
    content: str
    sender: str
    created_at: str
    citations: Optional[List] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Chat — request bodies
# ---------------------------------------------------------------------------

class ChatCreate(BaseModel):
    title: str = "New Chat"
    specialty: Optional[str] = None
    severity: Optional[str] = None

class ChatUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    specialty: Optional[str] = None
    severity: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat — responses
# ---------------------------------------------------------------------------

class ChatResponse(BaseModel):
    id: int
    title: str
    status: str
    specialty: Optional[str] = None
    severity: Optional[str] = None
    specialist_id: Optional[int] = None
    assigned_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    review_feedback: Optional[str] = None
    created_at: str
    user_id: int

    class Config:
        from_attributes = True

class ChatWithMessages(ChatResponse):
    messages: List[MessageResponse] = []


# ---------------------------------------------------------------------------
# Specialist workflow
# ---------------------------------------------------------------------------

class AssignRequest(BaseModel):
    specialist_id: int

class ReviewRequest(BaseModel):
    action: str          # "approve" | "reject"
    feedback: Optional[str] = None
