from src.rag.prompt import build_system_prompt, format_context
from src.retrieval.citation import Citation, CitedResult


def _sample_result() -> CitedResult:
    citation = Citation(
        title="Guideline",
        source_name="NICE",
        specialty="Cardiology",
        doc_type="guideline",
        section_path=["A", "B"],
        section_title="Therapy",
        page_start=1,
        page_end=2,
        source_url="https://example.com",
        doc_id="doc-1",
        chunk_id="chunk-1",
        content_type="text",
    )
    return CitedResult(
        chunk_id="chunk-1",
        text="Use aspirin in acute cases.",
        rerank_score=0.9,
        rrf_score=0.8,
        vector_score=0.7,
        keyword_rank=0.6,
        citation=citation,
    )


def test_build_system_prompt_mentions_context_and_citations() -> None:
    prompt = build_system_prompt().lower()
    assert "context" in prompt
    assert "citation" in prompt


def test_format_context_with_results() -> None:
    rendered = format_context([_sample_result()])
    assert rendered.startswith("[1] Guideline")
    assert "Section: Therapy" in rendered
    assert "A > B" in rendered
    assert "Use aspirin in acute cases." in rendered


def test_format_context_empty_returns_blank() -> None:
    assert format_context([]) == ""
