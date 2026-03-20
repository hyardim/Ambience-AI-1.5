from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.api import routes
from src.api.app import create_app


def test_answer_route_integration_returns_grounded_citations(
    monkeypatch,
):
    client = TestClient(create_app(), raise_server_exceptions=False)

    monkeypatch.setattr(
        routes,
        "retrieve_chunks",
        lambda query, top_k, specialty: [
            {
                "text": "Neurology guidance recommends ocrelizumab for active RRMS.",
                "score": 0.92,
                "doc_id": "doc-neuro-1",
                "metadata": {
                    "title": "NICE RRMS Guideline",
                    "source_name": "NICE",
                    "specialty": "neurology",
                    "publish_date": "2024-01-01",
                },
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local",
            score=0.9,
            threshold=0.5,
            reasons=["integration-test"],
        ),
    )

    async def fake_generate_answer(prompt, max_tokens, provider):
        assert "ocrelizumab" in prompt
        return "Use ocrelizumab when clinically appropriate [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    response = client.post(
        "/answer",
        json={
            "query": "What is recommended for active RRMS?",
            "specialty": "neurology",
            "patient_context": {"age": 34, "gender": "female"},
            "stream": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "ocrelizumab" in body["answer"]
    assert body["citations_used"][0]["source"] == "NICE RRMS Guideline"
    assert body["citations_used"][0]["publish_date"] == "2024-01-01"


def test_revise_route_integration_supports_file_context_only(monkeypatch):
    client = TestClient(create_app(), raise_server_exceptions=False)

    monkeypatch.setattr(routes, "retrieve_chunks", lambda query, top_k, specialty: [])
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="cloud",
            score=0.95,
            threshold=0.5,
            reasons=["file-context"],
        ),
    )

    async def fake_generate_answer(prompt, max_tokens, provider):
        assert "Uploaded MRI summary" in prompt
        return "Updated answer based on uploaded evidence."

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    response = client.post(
        "/revise",
        json={
            "original_query": "Should treatment change?",
            "previous_answer": "Original answer",
            "feedback": "Use the uploaded note",
            "file_context": "Uploaded MRI summary: new enhancing lesions.",
            "stream": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Updated answer based on uploaded evidence."
    assert body["citations_used"] == []


def test_ingest_route_integration_saves_file_and_returns_report(monkeypatch, tmp_path):
    client = TestClient(create_app(), raise_server_exceptions=False)

    monkeypatch.setattr(routes, "path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(
        routes,
        "load_sources",
        lambda path: {"NICE": {"specialty": "neurology"}},
    )

    captured = {}

    def fake_run_ingestion(*, input_path, source_name, db_url):
        captured["input_path"] = input_path
        captured["source_name"] = source_name
        captured["db_url"] = db_url
        return {
            "files_scanned": 1,
            "files_succeeded": 1,
            "files_failed": 0,
            "total_chunks": 3,
            "embeddings_succeeded": 3,
            "embeddings_failed": 0,
            "db": {"upserted": 3},
        }

    monkeypatch.setattr(routes, "run_ingestion", fake_run_ingestion)

    response = client.post(
        "/ingest",
        files={"file": ("guide.pdf", b"%PDF-1.4 test", "application/pdf")},
        data={"source_name": "NICE"},
    )

    assert response.status_code == 200
    saved_path = Path(captured["input_path"])
    assert saved_path.exists()
    assert saved_path.name == "guide.pdf"
    assert captured["source_name"] == "NICE"
    assert response.json()["total_chunks"] == 3
