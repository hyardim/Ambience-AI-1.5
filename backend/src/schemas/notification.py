from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class NotificationResponse(BaseModel):
    id: int
    type: str
    title: str
    body: Optional[str] = None
    chat_id: Optional[int] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True
