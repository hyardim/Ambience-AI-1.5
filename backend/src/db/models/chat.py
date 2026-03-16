from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.db.models.common import ENUM_VALUE_CONFIG, ChatStatus, utc_now


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="New Chat")
    status = Column(SQLEnum(ChatStatus, **ENUM_VALUE_CONFIG), default=ChatStatus.OPEN)
    specialty = Column(String, nullable=True)
    severity = Column(String, nullable=True)
    patient_context = Column(JSONB, nullable=True)
    specialist_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_feedback = Column(Text, nullable=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    user_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="chats", foreign_keys=[user_id])
    specialist = relationship(
        "User", back_populates="assigned_chats", foreign_keys=[specialist_id]
    )
    messages = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan"
    )
    files = relationship(
        "FileAttachment", back_populates="chat", cascade="all, delete-orphan"
    )

    @property
    def patient_age(self):
        return (self.patient_context or {}).get("age")

    @property
    def patient_gender(self):
        return (self.patient_context or {}).get("gender")

    @property
    def patient_notes(self):
        return (self.patient_context or {}).get("notes")
