"""Reusable async streaming generation helper for Ollama.

Yields token strings as they arrive from Ollama's /api/generate endpoint.
Both the legacy endpoints (/answer, /revise) and any future callers can
use this to stream LLM output without duplicating chunk-parsing logic.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from ..config import OLLAMA_BASE_URL, OLLAMA_MAX_TOKENS, OLLAMA_MODEL


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
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
        "keep_alive": -1,
        "options": {"num_predict": max_tokens or OLLAMA_MAX_TOKENS},
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
            ) as response:
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
