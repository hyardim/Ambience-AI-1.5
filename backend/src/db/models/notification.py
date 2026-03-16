from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.db.models.common import ENUM_VALUE_CONFIG, NotificationType, utc_now


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(SQLEnum(NotificationType, **ENUM_VALUE_CONFIG), nullable=False)
    title = Column(String, nullable=False)
    body = Column(String, nullable=True)
    chat_id = Column(
        Integer, ForeignKey("chats.id", ondelete="SET NULL"), nullable=True
    )
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", back_populates="notifications")
    chat = relationship("Chat")
