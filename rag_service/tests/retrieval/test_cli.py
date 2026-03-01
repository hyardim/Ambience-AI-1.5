from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from src.retrieval.citation import Citation, CitedResult
from src.retrieval.cli import main
from src.retrieval.query import RetrievalError

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_cited_result(chunk_id: str = "c1") -> CitedResult:
    return CitedResult(
        chunk_id=chunk_id,
        text="Urate-lowering therapy should be offered to patients with gout.",
        rerank_score=0.94,
        rrf_score=0.03,
        vector_score=0.85,
        keyword_rank=0.72,
        citation=Citation(
            title="Gout: diagnosis and management",
            source_name="NICE",
            specialty="rheumatology",
            doc_type="guideline",
            section_path=["Treatment", "Urate-lowering therapy"],
            section_title="Urate-lowering therapy",
            page_start=12,
            page_end=13,
            source_url="https://www.nice.org.uk/guidance/cg56",
            doc_id="doc_001",
            chunk_id=chunk_id,
            content_type="text",
        ),
    )
