from __future__ import annotations

import json

import pytest

from src.api import streaming as api_streaming
from src.generation import client, prompts, router


@pytest.mark.asyncio
async def test_router_selects_local_for_chunks_only():
    decision = router.select_generation_provider(
        query="Short RRMS question",
        retrieved_chunks=[{"score": 0.88}],
        severity="routine",
        prompt_length_chars=400,
    )
    assert decision.provider == "local"


@pytest.mark.asyncio
async def test_router_selects_cloud_for_file_context(monkeypatch):
    monkeypatch.setattr(router, "_cloud_available", lambda: True)
    # Large prompt length emulates file-context-heavy prompts.
    decision = router.select_generation_provider(
        query="Complex question",
        retrieved_chunks=[{"score": 0.35}, {"score": 0.34}],
        severity="urgent",
        prompt_length_chars=6000,
    )
    assert decision.provider == "cloud"


@pytest.mark.asyncio
async def test_prompt_building_includes_all_context():
    prompt = prompts.build_grounded_prompt(
        question="What should be monitored?",
        chunks=[
            {
                "text": "Monitor liver enzymes.",
                "metadata": {"title": "NICE", "source_name": "NICE"},
                "page_start": 5,
                "page_end": 5,
            },
            {
                "text": "Assess relapse frequency.",
                "metadata": {"title": "AAN", "source_name": "AAN"},
                "page_start": 7,
                "page_end": 7,
            },
        ],
        patient_context={"age": 42, "gender": "female", "notes": "new sensory relapse"},
    )
    assert "[1]" in prompt
    assert "[2]" in prompt
    assert "Age: 42" in prompt
    assert "Question: What should be monitored?" in prompt


@pytest.mark.asyncio
async def test_router_to_client_generates_answer(monkeypatch):
    async def fake_local(prompt: str, max_tokens: int | None = None):
        return "Generated response"

    monkeypatch.setattr(client, "_call_local_model", fake_local)

    decision = router.select_generation_provider(
        query="Simple question",
        retrieved_chunks=[{"score": 0.9}],
        prompt_length_chars=200,
    )
    prompt = prompts.build_grounded_prompt("Q", [{"text": "evidence", "metadata": {}}])
    answer = await client.generate_answer(
        prompt, max_tokens=64, provider=decision.provider
    )

    assert answer == "Generated response"


@pytest.mark.asyncio
async def test_streaming_generation_yields_chunks(monkeypatch):
    async def fake_stream_generate(prompt, max_tokens=None):
        yield "Hello "
        yield "world [1]"

    monkeypatch.setattr(api_streaming, "stream_generate", fake_stream_generate)

    citations = [
        type(
            "SearchResultLike",
            (),
            {
                "model_dump": lambda self: {
                    "score": 0.9,
                    "snippet": "evidence",
                    "source": "NICE",
                    "source_name": "NICE",
                    "source_url": "https://example",
                    "doc_id": "d1",
                    "chunk_id": "c1",
                    "section": "Treatment",
                    "page_start": 1,
                    "page_end": 1,
                    "publish_date": "2024-01-01",
                    "last_updated_date": "2024-02-01",
                }
            },
        )()
    ]

    lines = []
    async for line in api_streaming.streaming_generator(
        "prompt", 64, citations, provider="local"
    ):
        lines.append(json.loads(line))

    assert [entry["type"] for entry in lines[:2]] == ["chunk", "chunk"]
    assert lines[-1]["type"] == "done"
    assert "Hello world" in lines[-1]["answer"]
