from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.models.common import ENUM_VALUE_CONFIG, ChatStatus, utc_now

if TYPE_CHECKING:
    from src.db.models.file_attachment import FileAttachment
    from src.db.models.message import Message
    from src.db.models.user import User


class Chat(Base):
    __tablename__ = "chats"
    __table_args__ = (
        Index("ix_chats_user_id", "user_id"),
        Index("ix_chats_specialist_id", "specialist_id"),
        Index("ix_chats_status", "status"),
        Index("ix_chats_specialty", "specialty"),
        Index("ix_chats_created_at", "created_at"),
        Index("ix_chats_user_created_at", "user_id", "created_at"),
        Index("ix_chats_status_created_at", "status", "created_at"),
        Index(
            "ix_chats_user_archived_created_at", "user_id", "is_archived", "created_at"
        ),
        Index(
            "ix_chats_status_specialty_created_at", "status", "specialty", "created_at"
        ),
        Index(
            "ix_chats_specialist_status_assigned_at",
            "specialist_id",
            "status",
            "assigned_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String, default="New Chat")
    status: Mapped[ChatStatus] = mapped_column(
        SQLEnum(ChatStatus, **ENUM_VALUE_CONFIG), default=ChatStatus.OPEN
    )
    specialty: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    specialist_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )

    owner: Mapped[User | None] = relationship(
        "User", back_populates="chats", foreign_keys=[user_id]
    )
    specialist: Mapped[User | None] = relationship(
        "User", back_populates="assigned_chats", foreign_keys=[specialist_id]
    )
    messages: Mapped[list[Message]] = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan"
    )
    files: Mapped[list[FileAttachment]] = relationship(
        "FileAttachment", back_populates="chat", cascade="all, delete-orphan"
    )

    @property
    def patient_age(self) -> Any | None:
        return (self.patient_context or {}).get("age")

    @property
    def patient_gender(self) -> Any | None:
        return (self.patient_context or {}).get("gender")

    @property
    def patient_notes(self) -> Any | None:
        return (self.patient_context or {}).get("notes")
