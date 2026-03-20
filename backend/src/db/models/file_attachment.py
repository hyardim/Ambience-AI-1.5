from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.models.common import utc_now

if TYPE_CHECKING:
    from src.db.models.chat import Chat
    from src.db.models.user import User


class FileAttachment(Base):
    __tablename__ = "file_attachments"
    __table_args__ = (Index("ix_file_attachments_chat_id", "chat_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str | None] = mapped_column(String)
    file_size: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utc_now)
    chat_id: Mapped[int] = mapped_column(Integer, ForeignKey("chats.id"), nullable=False)
    uploader_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    chat: Mapped[Chat | None] = relationship("Chat", back_populates="files")
    uploader: Mapped[User | None] = relationship("User", back_populates="files")
