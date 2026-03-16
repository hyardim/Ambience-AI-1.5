from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# File attachment
# ---------------------------------------------------------------------------


class FileAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    created_at: str


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


class MessageBase(BaseModel):
    content: str


class MessageCreate(MessageBase):
    pass


class CitationResponse(BaseModel):
    doc_id: Optional[str] = None
    title: str
    source_name: str
    specialty: Optional[str] = None
    section_path: Optional[str | List[str]] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    source_url: Optional[str] = None
    creation_date: Optional[str] = None
    publish_date: Optional[str] = None
    last_updated_date: Optional[str] = None
    metadata: Optional[dict] = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    sender: str
    created_at: str
    citations: Optional[List[CitationResponse]] = None
    is_generating: bool = False
    review_status: Optional[str] = None
    review_feedback: Optional[str] = None
    reviewed_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat — request bodies
# ---------------------------------------------------------------------------


class ChatCreate(BaseModel):
    title: str = "New Chat"
    specialty: str
    severity: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None  # "male" | "female" | "other"
    patient_notes: Optional[str] = None  # free-text clinical notes


class ChatUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    specialty: Optional[str] = None
    severity: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat — responses
# ---------------------------------------------------------------------------


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: str
    specialty: Optional[str] = None
    severity: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    patient_notes: Optional[str] = None
    specialist_id: Optional[int] = None
    assigned_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    review_feedback: Optional[str] = None
    created_at: str
    user_id: int


class ChatWithMessages(ChatResponse):
    messages: List[MessageResponse] = []
    files: List[FileAttachmentResponse] = []


# ---------------------------------------------------------------------------
# Specialist workflow
# ---------------------------------------------------------------------------


class AssignRequest(BaseModel):
    specialist_id: int


class ReviewRequest(BaseModel):
    action: str  # "approve" | "reject" | "request_changes" | "manual_response"
    feedback: Optional[str] = None
    replacement_content: Optional[str] = (
        None  # required when action == "manual_response"
    )
    replacement_sources: Optional[List[str]] = None
