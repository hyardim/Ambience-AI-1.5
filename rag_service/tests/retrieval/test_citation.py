from __future__ import annotations

from typing import Any

import pytest

from src.retrieval.citation import (
    Citation,
    CitationError,
    CitedResult,
    assemble_citations,
    format_citation,
    format_section_path,
)
from src.retrieval.rerank import RankedResult

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_metadata(
    title: str = "Gout: diagnosis and management",
    source_name: str = "NICE",
    specialty: str = "rheumatology",
    doc_type: str = "guideline",
    source_url: str = "https://www.nice.org.uk/guidance/cg56",
    content_type: str = "text",
    section_path: list[str] | None = None,
    section_title: str = "Treatment",
    page_start: int | None = 12,
    page_end: int | None = 13,
) -> dict[str, Any]:
    return {
        "title": title,
        "source_name": source_name,
        "specialty": specialty,
        "doc_type": doc_type,
        "source_url": source_url,
        "content_type": content_type,
        "section_path": (
            section_path
            if section_path is not None
            else ["Treatment", "Urate-lowering therapy"]
        ),
        "section_title": section_title,
        "page_start": page_start,
        "page_end": page_end,
    }


def make_ranked_result(
    chunk_id: str = "chunk_001",
    text: str = "Allopurinol is recommended as first-line urate-lowering therapy.",
    rerank_score: float = 0.91,
    rrf_score: float = 0.03,
    vector_score: float | None = 0.85,
    keyword_rank: float | None = 0.72,
    metadata: dict[str, Any] | None = None,
) -> RankedResult:
    return RankedResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text=text,
        rerank_score=rerank_score,
        rrf_score=rrf_score,
        vector_score=vector_score,
        keyword_rank=keyword_rank,
        metadata=metadata if metadata is not None else make_metadata(),
    )


# -----------------------------------------------------------------------
# assemble_citations() tests
# -----------------------------------------------------------------------


class TestAssembleCitations:
    def test_returns_list_of_cited_results(self):
        results = [make_ranked_result("c1"), make_ranked_result("c2")]
        output = assemble_citations(results)
        assert isinstance(output, list)
        assert all(isinstance(r, CitedResult) for r in output)

    def test_citation_fields_populated_from_metadata(self):
        result = make_ranked_result(
            metadata=make_metadata(
                title="Gout: diagnosis and management",
                source_name="NICE",
                specialty="rheumatology",
                doc_type="guideline",
                source_url="https://www.nice.org.uk/guidance/cg56",
                content_type="text",
                section_path=["Treatment", "Urate-lowering therapy"],
                section_title="Urate-lowering therapy",
                page_start=12,
                page_end=13,
            )
        )
        output = assemble_citations([result])
        c = output[0].citation
        assert c.title == "Gout: diagnosis and management"
        assert c.source_name == "NICE"
        assert c.specialty == "rheumatology"
        assert c.doc_type == "guideline"
        assert c.source_url == "https://www.nice.org.uk/guidance/cg56"
        assert c.content_type == "text"
        assert c.section_path == ["Treatment", "Urate-lowering therapy"]
        assert c.section_title == "Urate-lowering therapy"
        assert c.page_start == 12
        assert c.page_end == 13
        assert c.chunk_id == result.chunk_id
        assert c.doc_id == result.doc_id

    def test_rerank_score_preserved(self):
        result = make_ranked_result(rerank_score=0.94)
        output = assemble_citations([result])
        assert output[0].rerank_score == 0.94

    def test_rrf_score_preserved(self):
        result = make_ranked_result(rrf_score=0.042)
        output = assemble_citations([result])
        assert output[0].rrf_score == 0.042

    def test_vector_score_preserved(self):
        result = make_ranked_result(vector_score=0.88)
        output = assemble_citations([result])
        assert output[0].vector_score == 0.88

    def test_keyword_rank_preserved(self):
        result = make_ranked_result(keyword_rank=0.55)
        output = assemble_citations([result])
        assert output[0].keyword_rank == 0.55

    def test_ordering_preserved_after_assembly(self):
        results = [
            make_ranked_result("c1", rerank_score=0.9),
            make_ranked_result("c2", rerank_score=0.7),
            make_ranked_result("c3", rerank_score=0.5),
        ]
        output = assemble_citations(results)
        assert [r.chunk_id for r in output] == ["c1", "c2", "c3"]

    def test_empty_input_returns_empty_list(self):
        assert assemble_citations([]) == []

    def test_missing_metadata_field_raises_citation_error(self):
        metadata = make_metadata()
        del metadata["source_url"]
        result = make_ranked_result(chunk_id="c1", metadata=metadata)
        with pytest.raises(CitationError) as exc_info:
            assemble_citations([result])
        assert exc_info.value.chunk_id == "c1"
        assert exc_info.value.missing_field == "source_url"

    def test_empty_section_path_uses_fallback(self):
        metadata = make_metadata(section_path=[])
        result = make_ranked_result(metadata=metadata)
        output = assemble_citations([result])
        assert output[0].citation.section_path == ["Unknown section"]

    def test_none_page_start_uses_fallback(self):
        metadata = make_metadata(page_start=None)
        result = make_ranked_result(metadata=metadata)
        output = assemble_citations([result])
        assert output[0].citation.page_start == 0

    def test_none_page_end_uses_fallback(self):
        metadata = make_metadata(page_end=None)
        result = make_ranked_result(metadata=metadata)
        output = assemble_citations([result])
        assert output[0].citation.page_end == 0

    def test_none_page_values_use_fallback(self):
        metadata = make_metadata(page_start=None, page_end=None)
        result = make_ranked_result(metadata=metadata)
        output = assemble_citations([result])
        assert output[0].citation.page_start == 0
        assert output[0].citation.page_end == 0

    def test_citation_error_message_contains_field_and_chunk(self):
        metadata = make_metadata()
        del metadata["title"]
        result = make_ranked_result(chunk_id="chunk_abc", metadata=metadata)
        with pytest.raises(CitationError) as exc_info:
            assemble_citations([result])
        assert "title" in str(exc_info.value)
        assert "chunk_abc" in str(exc_info.value)


# -----------------------------------------------------------------------
# format_section_path() tests
# -----------------------------------------------------------------------


class TestFormatSectionPath:
    def test_format_section_path_joins_with_arrow(self):
        result = format_section_path(["Treatment", "First-line therapy", "NSAIDs"])
        assert result == "Treatment > First-line therapy > NSAIDs"

    def test_format_section_path_single_element(self):
        result = format_section_path(["Treatment"])
        assert result == "Treatment"

    def test_format_section_path_empty_returns_unknown(self):
        result = format_section_path([])
        assert result == "Unknown section"

    def test_format_section_path_two_elements(self):
        result = format_section_path(["Treatment", "Urate-lowering therapy"])
        assert result == "Treatment > Urate-lowering therapy"


# -----------------------------------------------------------------------
# format_citation() tests
# -----------------------------------------------------------------------


class TestFormatCitation:
    def _make_citation(self, **kwargs: Any) -> Citation:
        defaults: dict[str, Any] = {
            "title": "Gout: diagnosis and management",
            "source_name": "NICE",
            "specialty": "rheumatology",
            "doc_type": "guideline",
            "section_path": ["Treatment", "Urate-lowering therapy"],
            "section_title": "Urate-lowering therapy",
            "page_start": 12,
            "page_end": 13,
            "source_url": "https://www.nice.org.uk/guidance/cg56",
            "doc_id": "doc_001",
            "chunk_id": "chunk_001",
            "content_type": "text",
        }
        defaults.update(kwargs)
        return Citation(**defaults)

    def test_format_citation_produces_correct_string(self):
        citation = self._make_citation()
        result = format_citation(citation)
        expected = (
            "Gout: diagnosis and management — NICE (rheumatology)\n"
            "Section: Treatment > Urate-lowering therapy\n"
            "Pages: 12–13\n"
            "Source: https://www.nice.org.uk/guidance/cg56"
        )
        assert result == expected

    def test_format_citation_uses_format_section_path(self):
        citation = self._make_citation(section_path=["A", "B", "C"])
        result = format_citation(citation)
        assert "A > B > C" in result

    def test_format_citation_empty_section_path_shows_unknown(self):
        citation = self._make_citation(section_path=[])
        result = format_citation(citation)
        assert "Unknown section" in result

    def test_format_citation_zero_pages(self):
        citation = self._make_citation(page_start=0, page_end=0)
        result = format_citation(citation)
        assert "Pages: 0–0" in result
