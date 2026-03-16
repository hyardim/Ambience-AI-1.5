from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.db.models.common import ENUM_VALUE_CONFIG, UserRole


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(SQLEnum(UserRole, **ENUM_VALUE_CONFIG), default=UserRole.GP)
    specialty = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    chats = relationship("Chat", back_populates="owner", foreign_keys="[Chat.user_id]")
    assigned_chats = relationship(
        "Chat", back_populates="specialist", foreign_keys="[Chat.specialist_id]"
    )
    audit_logs = relationship("AuditLog", back_populates="user")
    files = relationship("FileAttachment", back_populates="uploader")
    notifications = relationship("Notification", back_populates="user")
