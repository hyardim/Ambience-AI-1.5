from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from src.db.base import Base

# 1. Define our Roles and Statuses
class UserRole(str, enum.Enum):
    GP = "gp"
    SPECIALIST = "specialist"

class ChatStatus(str, enum.Enum):
    OPEN = "open"
    ESCALATED = "escalated"
    RESOLVED = "resolved"

# 2. Update User Table
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    
    # ✅ New Column: Role (Defaults to GP)
    role = Column(SQLEnum(UserRole), default=UserRole.GP, nullable=False)
    
    chats = relationship("Chat", back_populates="owner")

# 3. Update Chat Table
class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # ✅ New Column: Status (Defaults to Open)
    status = Column(SQLEnum(ChatStatus), default=ChatStatus.OPEN, nullable=False)

    owner = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")

# 4. Message Table (Unchanged)
class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(String, nullable=False)
    sender = Column(String, nullable=False)  # "user" or "ai"
    timestamp = Column(DateTime, default=datetime.utcnow)
    chat_id = Column(Integer, ForeignKey("chats.id"))

    chat = relationship("Chat", back_populates="messages")