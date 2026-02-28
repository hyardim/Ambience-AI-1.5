from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from src.retrieval.query import RetrievalError
from src.retrieval.keyword_search import KeywordSearchResult, keyword_search

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

QUERY = "methotrexate dosage"


def make_row(
    chunk_id: str = "chunk_001",
    doc_id: str = "doc_001",
    text: str = "Some clinical text.",
    rank: float = 0.72,
    specialty: str = "rheumatology",
    source_name: str = "NICE",
    doc_type: str = "guideline",
    source_url: str = "https://nice.org.uk",
    content_type: str = "text",
    section_title: str = "Treatment",
    title: str = "RA Guidelines",
    page_start: int = 1,
    page_end: int = 2,
    section_path: list[str] | None = None,
) -> tuple:
    return (
        chunk_id,
        doc_id,
        text,
        rank,
        specialty,
        source_name,
        doc_type,
        source_url,
        content_type,
        section_title,
        title,
        page_start,
        page_end,
        section_path or ["Treatment"],
    )