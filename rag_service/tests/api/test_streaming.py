from __future__ import annotations

import json

import pytest

from src.api.schemas import SearchResult
from src.api.streaming import ndjson_done_only, streaming_generator


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
        "src.api.streaming.generate_answer",
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
        "src.api.streaming.stream_generate",
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
    async for line in streaming_generator(
        "prompt",
        512,
        citations_retrieved,
        allow_uncited_answer=True,
    ):
        lines.append(json.loads(line.strip()))

    assert len(lines) == 4
    assert lines[0] == {"type": "chunk", "delta": "Hello"}
    assert lines[1] == {"type": "chunk", "delta": " "}
    assert lines[2] == {"type": "chunk", "delta": "world"}
    assert lines[3]["type"] == "done"
    assert lines[3]["answer"] == "Hello world"
    assert "citations_retrieved" in lines[3]


@pytest.mark.anyio
async def test_done_payload_keeps_empty_used_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_stream_generate(prompt: str, max_tokens: int | None = None):
        del prompt, max_tokens
        yield "No inline citations here"

    monkeypatch.setattr(
        "src.api.streaming.stream_generate",
        fake_stream_generate,
    )

    citations_retrieved = [
        SearchResult(text="evidence", source="guideline.pdf", score=0.9)
    ]

    lines = []
    async for line in streaming_generator("prompt", 128, citations_retrieved):
        lines.append(json.loads(line.strip()))

    assert lines[-1]["type"] == "done"
    assert lines[-1]["citations_used"] == []
    assert lines[-1]["citations"] == []


@pytest.mark.anyio
async def test_produces_error_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_stream(prompt: str, max_tokens: int | None = None):
        del prompt, max_tokens
        raise RuntimeError("model crashed")
        yield  # pragma: no cover

    monkeypatch.setattr(
        "src.api.streaming.stream_generate",
        failing_stream,
    )
    events: list[str] = []
    monkeypatch.setattr(
        "src.api.streaming.logger.exception",
        lambda message: events.append(str(message)),
    )

    lines = []
    async for line in streaming_generator("prompt", 512, []):
        lines.append(json.loads(line.strip()))

    assert len(lines) == 1
    assert lines[0]["type"] == "error"
    assert "model crashed" in lines[0]["error"]
    assert events == ["Streaming generation failed"]


@pytest.mark.anyio
async def test_ndjson_done_only_emits_done_payload() -> None:
    lines = []

    async for line in ndjson_done_only("Final answer"):
        lines.append(json.loads(line.strip()))

    assert lines == [
        {
            "type": "done",
            "answer": "Final answer",
            "citations_used": [],
            "citations_retrieved": [],
            "citations": [],
        }
    ]
