from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.db.models.common import utc_now


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_chat_id", "chat_id"),
        Index("ix_messages_sender", "sender"),
        Index("ix_messages_created_at", "created_at"),
    )

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
