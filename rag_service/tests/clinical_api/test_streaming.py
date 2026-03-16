from __future__ import annotations

import json

import pytest

from src.clinical_api.schemas import SearchResult
from src.clinical_api.streaming import streaming_generator


@pytest.mark.anyio
async def test_streaming_generator_uses_generate_answer_for_cloud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate_answer(
        prompt: str,
        max_tokens: int | None = None,
        provider: str = "local",
    ) -> str:
        assert provider == "cloud"
        return "Cloud answer [1]"

    monkeypatch.setattr(
        "src.clinical_api.streaming.generate_answer",
        fake_generate_answer,
    )
    citations = [SearchResult(text="A", source="S", score=0.9)]

    lines = []
    async for line in streaming_generator(
        "prompt",
        64,
        citations,
        provider="cloud",
    ):
        lines.append(line)

    assert len(lines) == 1
    assert '"type": "done"' in lines[0]


@pytest.mark.anyio
async def test_produces_chunks_then_done(monkeypatch: pytest.MonkeyPatch) -> None:
    tokens = ["Hello", " ", "world"]

    async def fake_stream_generate(prompt: str, max_tokens: int | None = None):
        del prompt, max_tokens
        for token in tokens:
            yield token

    monkeypatch.setattr(
        "src.clinical_api.streaming.stream_generate",
        fake_stream_generate,
    )

    citations_retrieved = [
        SearchResult(
            text="evidence",
            source="guideline.pdf",
            score=0.9,
        )
    ]

    lines = []
    async for line in streaming_generator("prompt", 512, citations_retrieved):
        lines.append(json.loads(line.strip()))

    assert len(lines) == 4
    assert lines[0] == {"type": "chunk", "delta": "Hello"}
    assert lines[1] == {"type": "chunk", "delta": " "}
    assert lines[2] == {"type": "chunk", "delta": "world"}
    assert lines[3]["type"] == "done"
    assert lines[3]["answer"] == "Hello world"
    assert "citations_retrieved" in lines[3]


@pytest.mark.anyio
async def test_produces_error_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_stream(prompt: str, max_tokens: int | None = None):
        del prompt, max_tokens
        raise RuntimeError("model crashed")
        yield  # pragma: no cover

    monkeypatch.setattr(
        "src.clinical_api.streaming.stream_generate",
        failing_stream,
    )

    lines = []
    async for line in streaming_generator("prompt", 512, []):
        lines.append(json.loads(line.strip()))

    assert len(lines) == 1
    assert lines[0]["type"] == "error"
    assert "model crashed" in lines[0]["error"]
