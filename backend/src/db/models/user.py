from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.models.common import ENUM_VALUE_CONFIG, UserRole

if TYPE_CHECKING:
    from src.db.models.audit import AuditLog
    from src.db.models.chat import Chat
    from src.db.models.file_attachment import FileAttachment
    from src.db.models.notification import Notification


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, **ENUM_VALUE_CONFIG), default=UserRole.GP
    )
    specialty: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    chats: Mapped[list[Chat]] = relationship(
        "Chat", back_populates="owner", foreign_keys="[Chat.user_id]"
    )
    assigned_chats: Mapped[list[Chat]] = relationship(
        "Chat", back_populates="specialist", foreign_keys="[Chat.specialist_id]"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship("AuditLog", back_populates="user")
    files: Mapped[list[FileAttachment]] = relationship(
        "FileAttachment", back_populates="uploader"
    )
    notifications: Mapped[list[Notification]] = relationship(
        "Notification", back_populates="user"
    )
