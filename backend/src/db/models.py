from datetime import datetime
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from src.db.base import Base


ENUM_VALUE_CONFIG = {
    "native_enum": False,
    "values_callable": lambda enum_cls: [member.value for member in enum_cls],
}


class UserRole(enum.Enum):
    GP = "gp"
    SPECIALIST = "specialist"
    ADMIN = "admin"


class NotificationType(enum.Enum):
    CHAT_ASSIGNED = "chat_assigned"
    SPECIALIST_MSG = "specialist_msg"
    CHAT_APPROVED = "chat_approved"
    CHAT_REJECTED = "chat_rejected"
    CHAT_REVISION = "chat_revision"


class ChatStatus(enum.Enum):
    OPEN = "open"
    SUBMITTED = "submitted"
    ASSIGNED = "assigned"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLOSED = "closed"
    FLAGGED = "flagged"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(SQLEnum(UserRole, **ENUM_VALUE_CONFIG), default=UserRole.GP)
    specialty = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=True, nullable=False)
    email_verified_at = Column(DateTime, nullable=True)

    chats = relationship("Chat", back_populates="owner", foreign_keys="[Chat.user_id]")
    assigned_chats = relationship(
        "Chat", back_populates="specialist", foreign_keys="[Chat.specialist_id]"
    )
    audit_logs = relationship("AuditLog", back_populates="user")
    files = relationship("FileAttachment", back_populates="uploader")
    notifications = relationship("Notification", back_populates="user")
    password_reset_tokens = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    email_verification_tokens = relationship(
        "EmailVerificationToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String)
    details = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_logs")


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

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="chats", foreign_keys=[user_id])
    specialist = relationship("User", back_populates="assigned_chats", foreign_keys=[specialist_id])

    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")
    files = relationship("FileAttachment", back_populates="chat", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    role = Column(String, nullable=True)
    sender = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    citations = Column(JSONB(none_as_null=True), nullable=True)
    is_generating = Column(Boolean, default=False, server_default="false")

    review_status = Column(String, nullable=True)
    review_feedback = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    chat_id = Column(Integer, ForeignKey("chats.id"))
    chat = relationship("Chat", back_populates="messages")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(SQLEnum(NotificationType, **ENUM_VALUE_CONFIG), nullable=False)
    title = Column(String, nullable=False)
    body = Column(String, nullable=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="SET NULL"), nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")
    chat = relationship("Chat")


class FileAttachment(Base):
    __tablename__ = "file_attachments"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String)
    file_size = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)

    chat_id = Column(Integer, ForeignKey("chats.id"))
    chat = relationship("Chat", back_populates="files")

    uploader_id = Column(Integer, ForeignKey("users.id"))
    uploader = relationship("User", back_populates="files")
