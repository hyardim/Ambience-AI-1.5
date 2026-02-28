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

# -----------------------------------------------------------------------
# Required fields — missing any of these raises CitationError
# -----------------------------------------------------------------------

_REQUIRED_FIELDS = (
    "title",
    "source_name",
    "specialty",
    "doc_type",
    "source_url",
    "content_type",
    "section_title",
)

# -----------------------------------------------------------------------
# Main function
# -----------------------------------------------------------------------


def assemble_citations(
    results: list[RankedResult],
) -> list[CitedResult]:
    """
    Assemble full citation metadata onto each reranked result.

    Extracts citation fields from result.metadata, applies fallbacks for
    empty section_path and None page values, and raises CitationError for
    any other missing required field.

    Args:
        results: Reranked results from rerank() / deduplicate()

    Returns:
        List of CitedResult in original order

    Raises:
        CitationError: If a required metadata field is missing for any result
    """
    pass