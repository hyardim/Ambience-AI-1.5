from datetime import datetime
from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

Severity = Literal["low", "medium", "high", "urgent"]
Gender = Literal["male", "female", "other"]
ReviewAction = Literal[
    "approve",
    "reject",
    "request_changes",
    "manual_response",
    "edit_response",
    "send_comment",
    "unassign",
]

# ---------------------------------------------------------------------------
# Patient context validation
# ---------------------------------------------------------------------------


class PatientContext(BaseModel):
    """Validated shape for the patient_context JSONB field on chats."""

    age: Optional[int] = Field(default=None, ge=0, le=150)
    gender: Optional[Gender] = None
    specialty: Optional[str] = None
    severity: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=5000)


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
    """Base schema for message content with whitespace validation."""

    content: str = Field(min_length=1, max_length=50_000)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        """Strip whitespace and reject empty/whitespace-only messages."""
        v = v.strip()
        if not v:
            raise ValueError("Message content must not be empty or whitespace-only")
        return v


class MessageCreate(MessageBase):
    pass


class CitationResponse(BaseModel):
    doc_id: Optional[str] = None
    title: Optional[str] = None
    source_name: Optional[str] = None
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
    title: str = Field(default="New Chat", min_length=1, max_length=200)
    specialty: str = Field(min_length=1, max_length=100)
    severity: Optional[Severity] = None
    patient_age: Optional[int] = Field(default=None, ge=0, le=150)
    patient_gender: Optional[Gender] = None
    patient_notes: Optional[str] = Field(default=None, max_length=10_000)


class ChatUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[str] = Field(default=None, max_length=50)
    specialty: Optional[str] = Field(default=None, max_length=100)
    severity: Optional[Severity] = None


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


class SourceEntry(BaseModel):
    """A source with an explicit display name and optional URL."""

    name: str
    url: Optional[str] = None


class ReviewRequest(BaseModel):
    action: ReviewAction
    feedback: Optional[str] = Field(default=None, max_length=10_000)
    replacement_content: Optional[str] = Field(default=None, max_length=50_000)
    replacement_sources: Optional[List[Union[str, SourceEntry]]] = None
    edited_content: Optional[str] = Field(default=None, max_length=50_000)

    @field_validator("replacement_sources", mode="before")
    @classmethod
    def coerce_source_entries(cls, v: Any) -> Any:
        """Accept plain strings *and* ``{name, url?}`` objects."""
        if v is None:
            return v
        if not isinstance(v, list):
            return v
        out: list[Any] = []
        for item in v:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and "name" in item:
                out.append(SourceEntry(**item))
            else:
                out.append(item)
        return out
