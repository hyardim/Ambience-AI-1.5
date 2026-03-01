from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserUpdateAdmin(BaseModel):
    full_name: Optional[str] = None
    specialty: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class AdminChatResponse(BaseModel):
    id: int
    title: str
    status: str
    specialty: Optional[str] = None
    severity: Optional[str] = None
    user_id: int
    owner_name: Optional[str] = None
    specialist_id: Optional[int] = None
    specialist_name: Optional[str] = None
    assigned_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    review_feedback: Optional[str] = None
    created_at: str


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    action: str
    category: str
    details: Optional[str] = None
    timestamp: datetime
