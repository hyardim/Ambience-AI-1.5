from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.db.models.common import utc_now


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    role = Column(String, nullable=True)
    sender = Column(String)
    created_at = Column(DateTime, default=utc_now)
    citations = Column(JSONB(none_as_null=True), nullable=True)
    is_generating = Column(Boolean, default=False, server_default="false")
    review_status = Column(String, nullable=True)
    review_feedback = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))

    chat = relationship("Chat", back_populates="messages")
