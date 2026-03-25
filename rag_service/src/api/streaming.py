from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from ..generation.client import ProviderName, generate_answer
from ..generation.streaming import stream_generate
from ..utils.logger import setup_logger
from .citations import extract_citation_results
from .schemas import SearchResult
from .services import NO_EVIDENCE_RESPONSE

logger = setup_logger(__name__)


async def streaming_generator(
    prompt: str,
    max_tokens: int,
    citations_retrieved: list[SearchResult],
    *,
    allow_uncited_answer: bool = False,
    provider: ProviderName = "local",
    query: str | None = None,
) -> AsyncGenerator[str, None]:
    """Yield NDJSON lines: ``chunk`` deltas then a final ``done`` payload."""
    accumulated = ""
    try:
        if provider == "local":
            async for token in stream_generate(prompt, max_tokens=max_tokens):
                accumulated += token
                yield json.dumps({"type": "chunk", "delta": token}) + "\n"
        else:
            accumulated = await generate_answer(
                prompt,
                max_tokens=max_tokens,
                provider=provider,
            )
    except Exception as exc:
        logger.exception("Streaming generation failed")
        yield json.dumps({"type": "error", "error": str(exc)}) + "\n"
        return

    renumbered_answer, citations_used = extract_citation_results(
        accumulated,
        citations_retrieved,
        strip_references=True,
        query=query,
    )
    refused = False
    if not renumbered_answer.strip() or (
        not citations_used and not allow_uncited_answer
    ):
        renumbered_answer = NO_EVIDENCE_RESPONSE
        refused = True

    # When the answer was allowed through (not refused), fall back to
    # citations_retrieved so the frontend can still display sources.
    final_citations: list[SearchResult]
    if citations_used:
        final_citations = citations_used
    elif not refused:
        final_citations = citations_retrieved
    else:
        final_citations = []

    yield (
        json.dumps(
            {
                "type": "done",
                "answer": renumbered_answer,
                "citations_used": [
                    citation.model_dump() for citation in citations_used
                ],
                "citations_retrieved": [
                    citation.model_dump() for citation in citations_retrieved
                ],
                "citations": [
                    citation.model_dump() for citation in final_citations
                ],
            }
        )
        + "\n"
    )


async def ndjson_done_only(
    answer: str,
    citations_retrieved: list[SearchResult] | None = None,
) -> AsyncGenerator[str, None]:
    """Single ``done`` line for cases where no streaming is needed."""
    yield (
        json.dumps(
            {
                "type": "done",
                "answer": answer,
                "citations_used": [],
                "citations_retrieved": [
                    citation.model_dump() for citation in (citations_retrieved or [])
                ],
                "citations": [],
            }
        )
        + "\n"
    )
