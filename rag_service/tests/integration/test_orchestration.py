from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.api import routes
from src.api.app import create_app


def _client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def _chunk():
    return {
        "text": "RRMS treatment recommendation",
        "score": 0.91,
        "doc_id": "doc-1",
        "metadata": {
            "title": "NICE RRMS Guideline",
            "source_name": "NICE",
            "source_url": "https://example.org",
            "specialty": "neurology",
            "doc_type": "guideline",
            "content_type": "text",
            "section_title": "Treatment",
            "section_path": ["Treatment"],
            "page_start": 1,
            "page_end": 1,
            "publish_date": "2024-01-01",
            "last_updated_date": "2024-02-01",
        },
        "page_start": 1,
        "page_end": 1,
    }


def test_orchestration_answer_full_pipeline(monkeypatch):
    client = _client()

    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [_chunk()],
    )
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: retrieved,
    )
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.2, threshold=0.5, reasons=["test"]
        ),
    )

    async def fake_generate_answer(prompt, max_tokens, provider):
        return "Use first-line DMT [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    resp = client.post(
        "/answer",
        json={"query": "First-line RRMS treatment?", "specialty": "neurology"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "[1]" in data["answer"]
    assert len(data["citations_retrieved"]) >= len(data["citations_used"]) >= 1


def test_orchestration_no_evidence_fallback(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        routes.api_services, "retrieve_chunks_advanced", lambda **kwargs: []
    )
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: retrieved,
    )

    resp = client.post(
        "/answer", json={"query": "unsupported topic", "specialty": "neurology"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == routes.NO_EVIDENCE_RESPONSE
    assert data["citations_used"] == []


def test_orchestration_revise_with_feedback(monkeypatch):
    client = _client()

    monkeypatch.setattr(
        routes,
        "retrieve_chunks",
        lambda original_query, top_k, specialty: [_chunk()],
    )
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: retrieved,
    )
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.2, threshold=0.5, reasons=["test"]
        ),
    )

    captured = {}

    async def fake_generate_answer(prompt, max_tokens, provider):
        captured["prompt"] = prompt
        return "Revised recommendation [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    resp = client.post(
        "/revise",
        json={
            "original_query": "Should we escalate?",
            "previous_answer": "Initial answer",
            "feedback": "Include monitoring",
            "specialty": "neurology",
        },
    )
    assert resp.status_code == 200
    assert "Include monitoring" in captured["prompt"]
    assert resp.json()["citations_used"]
