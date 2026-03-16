from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from src.config import llm_config
from src.generation.client import _auth_headers, _extract_chat_completion_text
from src.orchestration.prompt import build_system_prompt, format_context
from src.retrieval.citation import CitedResult


class GenerationError(Exception):
    def __init__(self, query: str, message: str) -> None:
        self.query = query
        self.message = message
        super().__init__(f"GENERATION | {query} | {message}")


class RAGResponse(BaseModel):
    answer: str
    sources: list[CitedResult]
    query: str
    model: str


def generate(
    query: str,
    context: list[CitedResult],
    settings: Any = llm_config,
) -> RAGResponse:
    """Call the LLM to generate a grounded answer.

    Raises GenerationError on model call failure.
    """

    base_url = getattr(settings, "llm_base_url", llm_config.llm_base_url).rstrip("/")
    api_key = getattr(settings, "llm_api_key", llm_config.llm_api_key)
    model = getattr(settings, "llm_model", llm_config.llm_model)
    max_tokens = getattr(settings, "llm_max_tokens", llm_config.llm_max_tokens)
    temperature = getattr(settings, "llm_temperature", llm_config.llm_temperature)
    timeout_seconds = getattr(
        settings, "llm_timeout_seconds", llm_config.llm_timeout_seconds
    )

    messages = [
        {"role": "system", "content": build_system_prompt()},
        {
            "role": "user",
            "content": f"Context:\n{format_context(context)}\n\nQuestion: {query}",
        },
    ]

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    try:
        resp = httpx.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers=_auth_headers(api_key),
            timeout=timeout_seconds,
        )
        resp.raise_for_status()
        answer = _extract_chat_completion_text(resp.json())
    except GenerationError:
        raise
    except Exception as e:  # pragma: no cover - defensive
        raise GenerationError(query=query, message=str(e)) from e

    return RAGResponse(answer=answer or "", sources=context, query=query, model=model)
