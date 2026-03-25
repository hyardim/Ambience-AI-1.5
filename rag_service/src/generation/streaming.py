"""Async streaming helper for Ollama."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from ..config import local_llm_config


async def stream_generate(
    prompt: str,
    max_tokens: int | None = None,
) -> AsyncIterator[str]:
    """Stream tokens from Ollama's ``/api/generate`` endpoint.

    Yields individual token strings.  The caller is responsible for
    accumulating them into the final answer.

    Raises ``RuntimeError`` on HTTP or connection failure.
    """
    payload = {
        "model": local_llm_config.model,
        "prompt": prompt,
        "stream": True,
        "keep_alive": -1,
        "options": {
            "num_predict": max_tokens or local_llm_config.max_tokens,
            "temperature": local_llm_config.temperature,
        },
    }

    try:
        async with (
            httpx.AsyncClient(
                timeout=local_llm_config.timeout_seconds
            ) as client,
            client.stream(
                "POST",
                f"{local_llm_config.base_url.rstrip('/')}/api/generate",
                json=payload,
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("response", "")
                if token:
                    yield token
                if chunk.get("done", False):
                    return
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Ollama streaming request failed: {exc}") from exc
