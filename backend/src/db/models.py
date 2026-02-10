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
    is_active = Column(Boolean, default=True)
    
    chats = relationship("Chat", back_populates="owner")
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
    
    # Metadata for Patient Context (e.g. {"age": 45, "condition": "diabetes"})
    patient_context = Column(JSONB, nullable=True) 
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="chats")
    
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