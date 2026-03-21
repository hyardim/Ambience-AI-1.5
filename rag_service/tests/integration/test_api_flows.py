from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.api import routes
from src.api.app import create_app
from src.generation.client import ModelGenerationError


def _client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def _sample_chunk(text: str = "Neurology guidance recommends ocrelizumab.") -> dict:
    return {
        "text": text,
        "score": 0.92,
        "doc_id": "doc-neuro-1",
        "metadata": {
            "title": "NICE RRMS Guideline",
            "source_name": "NICE",
            "specialty": "neurology",
            "publish_date": "2024-01-01",
            "source_url": "https://nice.example/ng220",
            "doc_type": "guideline",
            "content_type": "text",
            "section_title": "Treatment",
            "section_path": ["Treatment"],
            "page_start": 4,
            "page_end": 4,
        },
        "page_start": 4,
        "page_end": 4,
    }


def _route_cloud(*args, **kwargs):
    return SimpleNamespace(
        provider="cloud",
        score=0.95,
        threshold=0.5,
        reasons=["integration-test"],
    )


def _route_local(*args, **kwargs):
    return SimpleNamespace(
        provider="local",
        score=0.2,
        threshold=0.5,
        reasons=["integration-test"],
    )


def test_answer_returns_no_evidence_when_retrieval_empty(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        routes.api_services, "retrieve_chunks_advanced", lambda **kwargs: []
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)

    response = client.post(
        "/answer",
        json={"query": "What does this guideline say?", "specialty": "neurology"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == routes.NO_EVIDENCE_RESPONSE
    assert body["citations_used"] == []


def test_answer_streaming_returns_ndjson_chunks(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [_sample_chunk()],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "select_generation_provider", _route_local)

    async def fake_stream_generate(prompt, max_tokens=None):
        yield "chunk-1 "
        yield "chunk-2 [1]"

    monkeypatch.setattr("src.api.streaming.stream_generate", fake_stream_generate)

    response = client.post(
        "/answer",
        json={
            "query": "What is recommended for RRMS?",
            "specialty": "neurology",
            "stream": True,
        },
    )

    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert any('"type": "chunk"' in line for line in lines)
    assert any('"type": "done"' in line for line in lines)


def test_answer_with_patient_context_threads_into_prompt(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [_sample_chunk()],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "select_generation_provider", _route_local)

    captured_prompt = {}

    async def fake_generate_answer(prompt, max_tokens, provider):
        captured_prompt["value"] = prompt
        return "Grounded recommendation [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    response = client.post(
        "/answer",
        json={
            "query": "How should we escalate treatment?",
            "specialty": "neurology",
            "patient_context": {
                "age": 34,
                "gender": "female",
                "notes": "optic neuritis",
            },
        },
    )

    assert response.status_code == 200
    prompt = captured_prompt["value"]
    assert "Age: 34" in prompt
    assert "Gender: Female" in prompt
    assert "Clinical notes: optic neuritis" in prompt


def test_answer_file_context_only_uses_cloud_provider(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        routes.api_services, "retrieve_chunks_advanced", lambda **kwargs: []
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)

    selected = {}

    def fake_select_generation_provider(**kwargs):
        selected["provider"] = "cloud"
        selected["kwargs"] = kwargs
        return _route_cloud()

    monkeypatch.setattr(
        routes, "select_generation_provider", fake_select_generation_provider
    )

    async def fake_generate_answer(prompt, max_tokens, provider):
        return "Answer from uploaded context."

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    response = client.post(
        "/answer",
        json={
            "query": "Summarise uploaded findings",
            "specialty": "neurology",
            "file_context": "Uploaded MRI summary with active lesions.",
        },
    )

    assert response.status_code == 200
    assert selected["provider"] == "cloud"
    assert selected["kwargs"]["retrieved_chunks"] == []


def test_answer_retry_on_retryable_generation_error(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [_sample_chunk()],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "select_generation_provider", _route_local)
    monkeypatch.setattr(routes.retry_config, "retry_enabled", True)

    async def fake_generate_answer(prompt, max_tokens, provider):
        raise ModelGenerationError("temporary outage", retryable=True)

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes, "create_retry_job", lambda **kwargs: ("job-123", "queued")
    )

    response = client.post(
        "/answer",
        json={"query": "Need treatment plan", "specialty": "neurology"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"]
    assert payload["status"] == "queued"


def test_revise_with_feedback_and_chunks(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        routes,
        "retrieve_chunks",
        lambda original_query, top_k, specialty: [_sample_chunk()],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "select_generation_provider", _route_local)

    captured = {}

    async def fake_generate_answer(prompt, max_tokens, provider):
        captured["prompt"] = prompt
        return "Revised answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    response = client.post(
        "/revise",
        json={
            "original_query": "Should treatment change?",
            "previous_answer": "Original answer",
            "feedback": "Include monitoring advice",
            "specialty": "neurology",
        },
    )

    assert response.status_code == 200
    assert "Include monitoring advice" in captured["prompt"]
    assert "Original answer" in captured["prompt"]


def test_revise_streaming(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        routes,
        "retrieve_chunks",
        lambda original_query, top_k, specialty: [_sample_chunk()],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "select_generation_provider", _route_local)

    async def fake_stream_generate(prompt, max_tokens=None):
        yield "revise-chunk [1]"

    monkeypatch.setattr("src.api.streaming.stream_generate", fake_stream_generate)

    response = client.post(
        "/revise",
        json={
            "original_query": "Can we optimise this answer?",
            "previous_answer": "Baseline answer",
            "feedback": "Tighten recommendation",
            "stream": True,
        },
    )

    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert any('"type": "chunk"' in line for line in lines)
    assert any('"type": "done"' in line for line in lines)


def test_query_returns_structured_search_results(monkeypatch):
    client = _client()

    monkeypatch.setattr(
        routes,
        "retrieve_chunks",
        lambda query, top_k, specialty: [
            {
                "text": "Guideline text",
                "score": 0.91,
                "doc_id": "doc-1",
                "chunk_id": "chunk-1",
                "metadata": {
                    "title": "NICE Guideline",
                    "source_name": "NICE",
                    "source_url": "https://example.com",
                    "specialty": "neurology",
                    "doc_type": "guideline",
                    "section_title": "Diagnosis",
                    "section_path": ["Diagnosis"],
                    "page_start": 2,
                    "page_end": 3,
                    "publish_date": "2024-01-01",
                    "last_updated_date": "2024-02-01",
                },
                "page_start": 2,
                "page_end": 3,
            }
        ],
    )

    response = client.post(
        "/query",
        json={"query": "MS diagnosis", "top_k": 3, "specialty": "neurology"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["source"] == "NICE Guideline"
    assert payload[0]["doc_id"] == "doc-1"


def test_ingest_rejects_non_pdf_file():
    client = _client()

    response = client.post(
        "/ingest",
        files={"file": ("note.docx", b"docx-bytes", "application/vnd.openxmlformats")},
        data={"source_name": "NICE"},
    )

    assert response.status_code == 422


def test_protected_routes_reject_missing_api_key(monkeypatch):
    client = _client()
    monkeypatch.setenv("RAG_INTERNAL_API_KEY", "secret-test-key")

    response = client.post(
        "/answer",
        json={"query": "Any recommendation?", "specialty": "neurology"},
    )

    assert response.status_code == 401


def test_answer_route_integration_returns_grounded_citations(
    monkeypatch,
):
    client = _client()

    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [_sample_chunk()],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "select_generation_provider", _route_local)

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
    client = _client()

    monkeypatch.setattr(routes, "retrieve_chunks", lambda query, top_k, specialty: [])
    monkeypatch.setattr(routes, "select_generation_provider", _route_cloud)

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
    client = _client()

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
    assert captured["input_path"].exists()
    assert captured["input_path"].name == "guide.pdf"
    assert captured["source_name"] == "NICE"
    assert response.json()["total_chunks"] == 3
