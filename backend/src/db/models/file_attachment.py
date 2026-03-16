from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.db.models.common import utc_now


class FileAttachment(Base):
    __tablename__ = "file_attachments"
    __table_args__ = (Index("ix_file_attachments_chat_id", "chat_id"),)

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String)
    file_size = Column(Integer)
    created_at = Column(DateTime, default=utc_now)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    uploader_id = Column(Integer, ForeignKey("users.id"))

    chat = relationship("Chat", back_populates="files")
    uploader = relationship("User", back_populates="files")
