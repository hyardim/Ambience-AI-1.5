from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..utils.logger import setup_logger
from .rerank import RankedResult

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------


class CitationError(Exception):
    def __init__(self, chunk_id: str, missing_field: str) -> None:
        self.chunk_id = chunk_id
        self.missing_field = missing_field
        super().__init__(
            f"Missing citation field '{missing_field}' for chunk {chunk_id}"
        )

# -----------------------------------------------------------------------
# Pydantic models
# -----------------------------------------------------------------------


class Citation(BaseModel):
    title: str
    source_name: str
    specialty: str
    doc_type: str
    section_path: list[str]
    section_title: str
    page_start: int
    page_end: int
    source_url: str
    doc_id: str
    chunk_id: str
    content_type: str


class CitedResult(BaseModel):
    chunk_id: str
    text: str
    rerank_score: float
    rrf_score: float
    vector_score: float | None
    keyword_rank: float | None
    citation: Citation