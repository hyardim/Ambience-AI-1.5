from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from src.retrieval.filters import FilterConfig, apply_filters
from src.retrieval.fusion import FusedResult

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_result(
    chunk_id: str = "chunk_001",
    rrf_score: float = 0.03,
    vector_score: float | None = 0.85,
    keyword_ts_rank: float | None = None,
    specialty: str = "rheumatology",
    source_name: str = "NICE",
    doc_type: str = "guideline",
    content_type: str = "text",
) -> FusedResult:
    return FusedResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text="Some clinical text.",
        rrf_score=rrf_score,
        vector_score=vector_score,
        keyword_rank=keyword_ts_rank,
        metadata={
            "specialty": specialty,
            "source_name": source_name,
            "doc_type": doc_type,
            "content_type": content_type,
            "source_url": "https://nice.org.uk",
            "section_title": "Treatment",
            "title": "RA Guidelines",
            "page_start": 1,
            "page_end": 2,
            "section_path": ["Treatment"],
        },
    )
