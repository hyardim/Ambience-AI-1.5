from __future__ import annotations

import re
from typing import Any

from ..utils.citation_utils import (
    extract_citation_indices,
    rewrite_citations,
)


def select_citations(
    answer_text: str,
    citations_retrieved: list[dict[str, Any]],
    strip_references: bool,
) -> tuple[str, list[dict[str, Any]]]:
    used_indices = extract_citation_indices(answer_text)
    sorted_used = sorted(i for i in used_indices if 1 <= i <= len(citations_retrieved))
    citations_used = [citations_retrieved[i - 1] for i in sorted_used]
    renumber_map = {original: new for new, original in enumerate(sorted_used, start=1)}
    rewritten = rewrite_citations(answer_text, renumber_map)
    if strip_references:
        rewritten = re.sub(
            r"\n+\s*References?:.*",
            "",
            rewritten,
            flags=re.DOTALL | re.IGNORECASE,
        ).rstrip()
    return rewritten, citations_used


def build_answer_response(
    *,
    answer_text: str,
    prompt_label: str,
    citations_retrieved: list[dict[str, Any]],
) -> dict[str, Any]:
    rewritten_answer, citations_used = select_citations(
        answer_text,
        citations_retrieved,
        strip_references=True,
    )
    answer = (
        f"[Prompt: {prompt_label}]\n\n{rewritten_answer}"
        if prompt_label
        else rewritten_answer
    )
    return {
        "answer": answer,
        "citations_used": citations_used,
        "citations_retrieved": citations_retrieved,
        "citations": citations_used,
    }


def build_revise_response(
    *,
    answer_text: str,
    citations_retrieved: list[dict[str, Any]],
) -> dict[str, Any]:
    rewritten_answer, citations_used = select_citations(
        answer_text,
        citations_retrieved,
        strip_references=False,
    )
    return {
        "answer": rewritten_answer,
        "citations_used": citations_used,
        "citations_retrieved": citations_retrieved,
        "citations": citations_used,
    }
