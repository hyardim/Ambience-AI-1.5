from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from src.db.base import Base

# --- Enums ---
class UserRole(enum.Enum):
    GP = "gp"
    SPECIALIST = "specialist"
    ADMIN = "admin"

class ChatStatus(enum.Enum):
    OPEN = "open"
    SUBMITTED = "submitted"      # GP submitted for specialist review
    ASSIGNED = "assigned"        # Specialist has been assigned
    REVIEWING = "reviewing"      # Specialist is actively reviewing
    APPROVED = "approved"        # Specialist approved the AI response
    REJECTED = "rejected"        # Specialist rejected / requested changes
    CLOSED = "closed"
    FLAGGED = "flagged"

# --- 1. User Management ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(SQLEnum(UserRole), default=UserRole.GP)
    specialty = Column(String, nullable=True)   # e.g. "neurology", "rheumatology"
    is_active = Column(Boolean, default=True)

    chats = relationship("Chat", back_populates="owner")
    assigned_chats = relationship("Chat", back_populates="specialist", foreign_keys="Chat.specialist_id")
    audit_logs = relationship("AuditLog", back_populates="user")
    files = relationship("FileAttachment", back_populates="uploader")

# --- 2. Compliance (Audit) ---
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String) # e.g. "LOGIN", "UPLOAD"
    details = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="audit_logs")

# --- 3. Conversation & Data ---
class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="New Chat")
    status = Column(SQLEnum(ChatStatus), default=ChatStatus.OPEN)

    # Clinical context
    specialty = Column(String, nullable=True)    # e.g. "neurology"
    severity = Column(String, nullable=True)     # "routine" | "urgent" | "emergency"

    # Patient metadata (free-form JSON, e.g. {"age": 45, "condition": "diabetes"})
    patient_context = Column(JSONB, nullable=True)

    # Specialist assignment
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
    sender = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # The "Magic Box" for RAG evidence
    citations = Column(JSONB, nullable=True) 
    
    chat_id = Column(Integer, ForeignKey("chats.id"))
    chat = relationship("Chat", back_populates="messages")

# --- 4. File Uploads ---
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