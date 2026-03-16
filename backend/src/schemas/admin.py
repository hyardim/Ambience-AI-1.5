from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DailyCount(BaseModel):
    date: str
    count: int


class AdminStatsResponse(BaseModel):
    total_ai_responses: int
    rag_grounded_responses: int
    specialist_responses: int
    active_consultations: int
    chats_by_status: dict
    chats_by_specialty: dict
    active_users_by_role: dict
    daily_ai_queries: list[DailyCount]


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
    owner_identifier: Optional[str] = None
    specialist_id: Optional[int] = None
    specialist_identifier: Optional[str] = None
    assigned_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    review_feedback: Optional[str] = None
    created_at: str


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    user_identifier: Optional[str] = None
    action: str
    category: str
    details: Optional[str] = None
    timestamp: datetime
