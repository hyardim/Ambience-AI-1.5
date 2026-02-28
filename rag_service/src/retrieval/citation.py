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
    if not results:
        return []

    logger.debug(f"Assembling citations for {len(results)} results")

    cited: list[CitedResult] = []
    for result in results:
        citation = _build_citation(result)
        cited.append(
            CitedResult(
                chunk_id=result.chunk_id,
                text=result.text,
                rerank_score=result.rerank_score,
                rrf_score=result.rrf_score,
                vector_score=result.vector_score,
                keyword_rank=result.keyword_rank,
                citation=citation,
            )
        )

    logger.debug("Citation assembly complete")
    return cited


# -----------------------------------------------------------------------
# Public helpers
# -----------------------------------------------------------------------


def format_section_path(section_path: list[str]) -> str:
    """
    Join section path list with ' > ' for display.

    Args:
        section_path: Ordered list of section hierarchy strings

    Returns:
        Human-readable section path string, or "Unknown section" if empty
    """
    if not section_path:
        return "Unknown section"
    return " > ".join(section_path)


def format_citation(citation: Citation) -> str:
    """
    Produce a human-readable citation string.

    Args:
        citation: Citation Pydantic model with source attribution fields

    Returns:
        Multi-line citation string
    """
    section = format_section_path(citation.section_path)
    return (
        f"{citation.title} — {citation.source_name} ({citation.specialty})\n"
        f"Section: {section}\n"
        f"Pages: {citation.page_start}–{citation.page_end}\n"
        f"Source: {citation.source_url}"
    )


# -----------------------------------------------------------------------
# Private helpers
# -----------------------------------------------------------------------


def _build_citation(result: RankedResult) -> Citation:
    """Extract and validate citation fields from result metadata."""
    metadata: dict[str, Any] = result.metadata

    for field in _REQUIRED_FIELDS:
        if metadata.get(field) is None:
            raise CitationError(chunk_id=result.chunk_id, missing_field=field)

    section_path = metadata.get("section_path")
    if not section_path:
        logger.warning(
            f"Empty section_path for chunk '{result.chunk_id}' "
            f"— falling back to ['Unknown section']"
        )
        section_path = ["Unknown section"]

    page_start = metadata.get("page_start")
    if page_start is None:
        logger.warning(
            f"None page_start for chunk '{result.chunk_id}' — falling back to 0"
        )
        page_start = 0

    page_end = metadata.get("page_end")
    if page_end is None:
        logger.warning(
            f"None page_end for chunk '{result.chunk_id}' — falling back to 0"
        )
        page_end = 0

    return Citation(
        title=metadata["title"],
        source_name=metadata["source_name"],
        specialty=metadata["specialty"],
        doc_type=metadata["doc_type"],
        section_path=section_path,
        section_title=metadata["section_title"],
        page_start=page_start,
        page_end=page_end,
        source_url=metadata["source_url"],
        doc_id=result.doc_id,
        chunk_id=result.chunk_id,
        content_type=metadata["content_type"],
    )
