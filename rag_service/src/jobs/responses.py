from __future__ import annotations

import re
from typing import Any

_CITATION_RE = re.compile(r"\[[\d,\s\-]+\]")


def parse_citation_group(raw: str) -> list[int]:
    numbers: list[int] = []
    for part in raw.split(","):
        token = part.strip()
        if "-" in token:
            try:
                start_str, end_str = token.split("-", 1)
                start, end = int(start_str), int(end_str)
                numbers.extend(range(start, end + 1))
            except ValueError:
                continue
            continue
        try:
            numbers.append(int(token))
        except ValueError:
            continue
    return numbers


def extract_citation_indices(text: str) -> set[int]:
    return {
        n
        for match in _CITATION_RE.findall(text)
        for n in parse_citation_group(match[1:-1])
    }


def rewrite_citations(text: str, renumber_map: dict[int, int]) -> str:
    def _rewrite(match: re.Match[str]) -> str:
        numbers = parse_citation_group(match.group(0)[1:-1])
        kept = sorted({renumber_map[n] for n in numbers if n in renumber_map})
        return f"[{', '.join(str(k) for k in kept)}]" if kept else ""

    return _CITATION_RE.sub(_rewrite, text)


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
