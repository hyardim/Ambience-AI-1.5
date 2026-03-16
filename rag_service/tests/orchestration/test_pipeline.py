from src.orchestration.generate import RAGResponse
from src.orchestration.pipeline import ask
from src.retrieval.citation import Citation, CitedResult


def _response() -> RAGResponse:
    citation = Citation(
        title="Guide",
        source_name="NICE",
        specialty="Cardiology",
        doc_type="guideline",
        section_path=["Intro"],
        section_title="Intro",
        page_start=1,
        page_end=1,
        source_url="https://example.com",
        doc_id="doc-1",
        chunk_id="chunk-1",
        content_type="text",
    )
    source = CitedResult(
        chunk_id="chunk-1",
        text="context",
        rerank_score=0.5,
        rrf_score=0.4,
        vector_score=0.3,
        keyword_rank=0.2,
        citation=citation,
    )
    return RAGResponse(
        answer="done",
        sources=[source],
        query="q",
        model="model-x",
    )


def test_ask_wires_retrieve_and_generate(monkeypatch) -> None:
    calls: dict[str, dict] = {"retrieve": {}, "generate": {}}
    context = _response().sources

    def fake_retrieve(**kwargs):
        calls["retrieve"] = kwargs
        return context

    def fake_generate(**kwargs):
        calls["generate"] = kwargs
        return _response()

    monkeypatch.setattr("src.orchestration.pipeline.retrieve", fake_retrieve)
    monkeypatch.setattr("src.orchestration.pipeline.generate", fake_generate)

    result = ask(
        query="q",
        db_url="postgresql://x",
        top_k=3,
        specialty="cardio",
        source_name="n",
        doc_type="pdf",
        score_threshold=0.4,
        expand_query=True,
        settings={"k": "v"},
    )

    assert result.answer == "done"
    assert calls["retrieve"]["db_url"] == "postgresql://x"
    assert calls["retrieve"]["top_k"] == 3
    assert calls["retrieve"]["specialty"] == "cardio"
    assert calls["retrieve"]["source_name"] == "n"
    assert calls["retrieve"]["doc_type"] == "pdf"
    assert calls["retrieve"]["score_threshold"] == 0.4
    assert calls["retrieve"]["expand_query"] is True
    assert calls["generate"]["query"] == "q"
    assert calls["generate"]["context"] == context
    assert calls["generate"]["settings"] == {"k": "v"}


def test_ask_returns_polite_when_no_context(monkeypatch) -> None:
    calls: dict[str, dict] = {"retrieve": {}, "generate": {}}

    def fake_retrieve(**kwargs):
        calls["retrieve"] = kwargs
        return []

    def fake_generate(**kwargs):
        calls["generate"] = kwargs
        raise AssertionError("generate should not be called when no context")

    monkeypatch.setattr("src.orchestration.pipeline.retrieve", fake_retrieve)
    monkeypatch.setattr("src.orchestration.pipeline.generate", fake_generate)

    result = ask(query="q", db_url="postgresql://x")

    assert result.sources == []
    assert "sufficient supporting sources" in result.answer.lower()
    assert calls["generate"] == {}
