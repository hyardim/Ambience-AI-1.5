from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.models.common import utc_now

if TYPE_CHECKING:
    from src.db.models.chat import Chat


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_chat_id", "chat_id"),
        Index("ix_messages_sender", "sender"),
        Index("ix_messages_created_at", "created_at"),
        Index("ix_messages_chat_created_at", "chat_id", "created_at"),
        Index(
            "ix_messages_chat_sender_review_created_at",
            "chat_id",
            "sender",
            "review_status",
            "created_at",
        ),
        Index(
            "ix_messages_chat_sender_generating", "chat_id", "sender", "is_generating"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    content: Mapped[str | None] = mapped_column(Text)
    # Legacy column — retained for backward compatibility with existing data
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    sender: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utc_now)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    is_generating: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    is_error: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    review_status: Mapped[str | None] = mapped_column(String, nullable=True)
    review_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    chat_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chats.id"), nullable=False
    )

    chat: Mapped[Chat | None] = relationship("Chat", back_populates="messages")
