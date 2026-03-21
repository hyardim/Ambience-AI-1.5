from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..config import llm_config
from ..generation.client import _request_chat_completion_sync
from ..retrieval.citation import CitedResult
from .prompt import build_system_prompt, format_context


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
    evidence_note: str | None = None,
) -> RAGResponse:
    """Call the LLM to generate a grounded answer.

    Raises GenerationError on model call failure.
    """

    model = getattr(settings, "llm_model", llm_config.llm_model)
    max_tokens = getattr(settings, "llm_max_tokens", llm_config.llm_max_tokens)
    prompt_parts = [build_system_prompt()]
    if evidence_note:
        prompt_parts.append(f"Evidence note: {evidence_note}")
    prompt_parts.append(f"Context:\n{format_context(context)}\n\nQuestion: {query}")
    prompt = "\n\n".join(prompt_parts)

    try:
        answer = _request_chat_completion_sync(
            provider="cloud",
            base_url=getattr(settings, "llm_base_url", llm_config.llm_base_url),
            api_key=getattr(settings, "llm_api_key", llm_config.llm_api_key),
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=getattr(
                settings,
                "llm_temperature",
                llm_config.llm_temperature,
            ),
            timeout_seconds=getattr(
                settings,
                "llm_timeout_seconds",
                llm_config.llm_timeout_seconds,
            ),
        )
    except GenerationError:
        raise
    except Exception as e:  # pragma: no cover
        raise GenerationError(query=query, message=str(e)) from e

    return RAGResponse(answer=answer or "", sources=context, query=query, model=model)
