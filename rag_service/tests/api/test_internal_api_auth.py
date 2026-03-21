from fastapi.testclient import TestClient

from src.api import routes as api_routes
from src.api.app import create_app


def test_query_requires_internal_api_key_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("RAG_INTERNAL_API_KEY", "secret-key")

    app = create_app()
    monkeypatch.setattr(api_routes, "retrieve_chunks", lambda *args, **kwargs: [])
    client = TestClient(app)

    unauthenticated = client.post("/query", json={"query": "hello", "top_k": 1})
    assert unauthenticated.status_code == 401

    authenticated = client.post(
        "/query",
        json={"query": "hello", "top_k": 1},
        headers={"X-Internal-API-Key": "secret-key"},
    )
    assert authenticated.status_code == 200
    assert authenticated.json() == []


def test_health_does_not_require_internal_api_key(monkeypatch) -> None:
    monkeypatch.setenv("RAG_INTERNAL_API_KEY", "secret-key")

    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
