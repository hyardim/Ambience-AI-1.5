from src.services.rag_client import build_rag_headers


def test_build_rag_headers_with_internal_key_and_idempotency(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.services.rag_client.settings.RAG_INTERNAL_API_KEY",
        "internal-key",
    )

    headers = build_rag_headers(idempotency_key="abc123")

    assert headers == {
        "X-Internal-API-Key": "internal-key",
        "Idempotency-Key": "abc123",
    }


def test_build_rag_headers_without_optional_values(monkeypatch) -> None:
    monkeypatch.setattr("src.services.rag_client.settings.RAG_INTERNAL_API_KEY", "")

    headers = build_rag_headers()

    assert headers == {}
