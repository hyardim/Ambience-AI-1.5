from __future__ import annotations

import pytest

from src.clinical_api.schemas import SearchResult
from src.clinical_api.services import (
    embed_query_text,
    filter_chunks,
    retrieve_chunks,
    to_search_result,
)


def test_filter_chunks_drops_low_quality_hits() -> None:
    kept = {
        "text": "migraine treatment guidance",
        "score": 0.9,
        "metadata": {"source_path": "/tmp/doc.pdf"},
    }
    dropped = {
        "text": "supplementary material",
        "score": 0.1,
        "metadata": {},
    }

    filtered = filter_chunks("migraine treatment", [kept, dropped])

    assert filtered == [kept]


def test_retrieve_chunks_passes_embedding_and_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search_calls: list[tuple[list[float], int, str | None]] = []
    monkeypatch.setattr(
        "src.clinical_api.services.embed_query_text",
        lambda query: [0.1, 0.2] if query == "headache" else [9.9],
    )

    def fake_search(
        vector: list[float],
        *,
        limit: int,
        specialty: str | None,
    ) -> list[dict[str, object]]:
        search_calls.append((vector, limit, specialty))
        return [{"text": "chunk", "score": 0.8, "metadata": {}}]

    monkeypatch.setattr("src.clinical_api.services.search_similar_chunks", fake_search)

    result = retrieve_chunks("headache", top_k=3, specialty="neurology")

    assert result == [{"text": "chunk", "score": 0.8, "metadata": {}}]
    assert search_calls == [([0.1, 0.2], 3, "neurology")]


def test_embed_query_text_uses_single_query_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = object()
    monkeypatch.setattr("src.clinical_api.services.get_embedding_model", lambda: model)

    def fake_embed_text(
        loaded_model: object,
        texts: list[str],
        *,
        batch_size: int,
    ) -> list[list[float]]:
        assert loaded_model is model
        assert texts == ["question"]
        assert batch_size == 1
        return [[0.3, 0.4]]

    monkeypatch.setattr("src.clinical_api.services.embed_text", fake_embed_text)

    assert embed_query_text("question") == [0.3, 0.4]


def test_to_search_result_uses_default_source_name() -> None:
    result = to_search_result({"text": "chunk", "score": 0.6})

    assert result == SearchResult(
        text="chunk",
        source="Unknown Source",
        score=0.6,
        metadata={},
    )
