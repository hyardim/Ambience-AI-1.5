import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.db.base import Base

ENUM_VALUE_CONFIG = {
    "native_enum": False,
    "values_callable": lambda enum_cls: [member.value for member in enum_cls],
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# --- Enums ---


class UserRole(enum.Enum):
    GP = "gp"
    SPECIALIST = "specialist"
    ADMIN = "admin"


class NotificationType(enum.Enum):
    CHAT_ASSIGNED = "chat_assigned"  # GP: chat was assigned to a specialist
    SPECIALIST_MSG = "specialist_msg"  # GP: specialist sent a message
    CHAT_APPROVED = "chat_approved"  # GP: specialist approved the chat
    CHAT_REJECTED = "chat_rejected"  # GP: specialist rejected the chat
    CHAT_REVISION = "chat_revision"  # GP: specialist requested changes to AI response


class ChatStatus(enum.Enum):
    OPEN = "open"
    SUBMITTED = "submitted"  # GP submitted for specialist review
    ASSIGNED = "assigned"  # Specialist has been assigned
    REVIEWING = "reviewing"  # Specialist is actively reviewing
    APPROVED = "approved"  # Specialist approved the AI response
    REJECTED = "rejected"  # Specialist rejected / requested changes
    CLOSED = "closed"
    FLAGGED = "flagged"
    ARCHIVED = "archived"  # Soft-archived by the user


# --- 1. User Management ---


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(SQLEnum(UserRole, **ENUM_VALUE_CONFIG), default=UserRole.GP)
    # e.g. "neurology", "rheumatology"
    specialty = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    chats = relationship("Chat", back_populates="owner", foreign_keys="[Chat.user_id]")
    assigned_chats = relationship(
        "Chat", back_populates="specialist", foreign_keys="[Chat.specialist_id]"
    )
    audit_logs = relationship("AuditLog", back_populates="user")
    files = relationship("FileAttachment", back_populates="uploader")
    notifications = relationship("Notification", back_populates="user")


# --- 2. Compliance (Audit) ---


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String)  # e.g. "LOGIN", "UPLOAD"
    details = Column(String, nullable=True)
    timestamp = Column(DateTime, default=utc_now)

    user = relationship("User", back_populates="audit_logs")


# --- 3. Conversation & Data ---


class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="New Chat")
    status = Column(SQLEnum(ChatStatus, **ENUM_VALUE_CONFIG), default=ChatStatus.OPEN)

    # Clinical context
    specialty = Column(String, nullable=True)  # e.g. "neurology"
    # "routine" | "urgent" | "emergency"
    severity = Column(String, nullable=True)

    # Patient metadata (free-form JSON, e.g. {"age": 45, "condition": "diabetes"})
    patient_context = Column(JSONB, nullable=True)

    # Specialist assignment
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


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    role = Column(String, nullable=True)
    sender = Column(String)
    created_at = Column(DateTime, default=utc_now)

    # The "Magic Box" for RAG evidence
    citations = Column(JSONB(none_as_null=True), nullable=True)

    # True while the RAG service is still generating the content
    is_generating = Column(Boolean, default=False, server_default="false")

    # Specialist review (AI messages only)
    # null | "approved" | "rejected"
    review_status = Column(String, nullable=True)
    review_feedback = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    chat_id = Column(Integer, ForeignKey("chats.id"))
    chat = relationship("Chat", back_populates="messages")


# --- 4. Notifications ---


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


# --- 5. File Uploads ---


class FileAttachment(Base):
    __tablename__ = "file_attachments"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String)
    file_size = Column(Integer)

    created_at = Column(DateTime, default=utc_now)

    chat_id = Column(Integer, ForeignKey("chats.id"))
    chat = relationship("Chat", back_populates="files")

    uploader_id = Column(Integer, ForeignKey("users.id"))
    uploader = relationship("User", back_populates="files")
