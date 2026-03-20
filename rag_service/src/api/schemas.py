from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..config import llm_config
from ..jobs.retry import RetryJobStatus


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    specialty: str | None = None
    severity: str | None = None


class SearchResult(BaseModel):
    text: str
    source: str
    score: float
    doc_id: str | None = None
    doc_version: str | None = None
    chunk_id: str | None = None
    chunk_index: int | None = None
    content_type: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_path: str | None = None
    creation_date: str | None = None
    publish_date: str | None = None
    last_updated_date: str | None = None
    metadata: dict[str, Any] | None = None


class AnswerRequest(QueryRequest):
    max_tokens: int = llm_config.llm_max_tokens
    patient_context: dict[str, Any] | None = None
    file_context: str | None = None
    file_context_truncated: bool = False
    stream: bool = False


class ReviseRequest(BaseModel):
    """Request body for the /revise endpoint."""

    original_query: str
    previous_answer: str
    feedback: str
    top_k: int = 5
    max_tokens: int = llm_config.llm_max_tokens
    patient_context: dict[str, Any] | None = None
    file_context: str | None = None
    specialty: str | None = None
    severity: str | None = None
    stream: bool = False


class AnswerResponse(BaseModel):
    answer: str
    citations_used: list[SearchResult]
    citations_retrieved: list[SearchResult]
    citations: list[SearchResult]


class IngestResponse(BaseModel):
    source_name: str
    filename: str
    files_scanned: int
    files_succeeded: int
    files_failed: int
    total_chunks: int
    embeddings_succeeded: int
    embeddings_failed: int
    db: dict[str, Any]


class RetryAcceptedResponse(BaseModel):
    job_id: str
    status: RetryJobStatus


class RetryJobResponse(BaseModel):
    job_id: str
    status: RetryJobStatus
    attempt_count: int
    last_error: str | None = None
    created_at: str
    updated_at: str
    response: dict[str, Any] | None = None
