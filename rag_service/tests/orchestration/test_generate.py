import pytest

from src.orchestration.generate import GenerationError, RAGResponse, generate
from src.retrieval.citation import Citation, CitedResult


def _context() -> list[CitedResult]:
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
    return [
        CitedResult(
            chunk_id="chunk-1",
            text="context text",
            rerank_score=0.5,
            rrf_score=0.4,
            vector_score=0.3,
            keyword_rank=0.2,
            citation=citation,
        )
    ]


def test_generate_returns_response(monkeypatch) -> None:
    captured = {}

    def fake_request(**kwargs):
        captured.update(kwargs)
        return "answer"

    monkeypatch.setattr(
        "src.orchestration.generate._request_chat_completion_sync",
        fake_request,
    )

    class DummySettings:
        llm_base_url = "http://localhost:1234"
        llm_api_key = "key"
        llm_model = "model-x"
        llm_max_tokens = 12
        llm_temperature = 0.5
        llm_timeout_seconds = 45.0

    response = generate(query="q", context=_context(), settings=DummySettings)

    assert isinstance(response, RAGResponse)
    assert response.answer == "answer"
    assert response.model == "model-x"
    assert captured["base_url"] == "http://localhost:1234"
    assert captured["api_key"] == "key"
    assert captured["model"] == "model-x"
    assert captured["max_tokens"] == 12
    assert captured["temperature"] == 0.5
    assert captured["timeout_seconds"] == 45.0


def test_generate_includes_evidence_note_in_prompt(monkeypatch) -> None:
    captured = {}

    def fake_request(**kwargs):
        captured.update(kwargs)
        return "answer"

    monkeypatch.setattr(
        "src.orchestration.generate._request_chat_completion_sync",
        fake_request,
    )

    generate(query="q", context=_context(), evidence_note="Evidence is limited.")

    prompt = captured["messages"][0]["content"]
    assert "Evidence note: Evidence is limited." in prompt


def test_generate_raises_generation_error(monkeypatch) -> None:
    def boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "src.orchestration.generate._request_chat_completion_sync",
        boom,
    )

    with pytest.raises(GenerationError):
        generate(query="q", context=_context())


def test_generate_reraises_generation_error(monkeypatch) -> None:
    def boom(**_kwargs):
        raise GenerationError(query="q", message="already wrapped")

    monkeypatch.setattr(
        "src.orchestration.generate._request_chat_completion_sync",
        boom,
    )

    with pytest.raises(GenerationError, match="already wrapped"):
        generate(query="q", context=_context())
