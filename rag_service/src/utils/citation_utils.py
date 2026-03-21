"""Shared citation parsing/rewriting helpers with no dependency on API schemas."""

from __future__ import annotations

import contextlib
import re

_CITATION_RE = re.compile(r"\[[\d,\s\-]+\]")


def parse_citation_group(raw: str) -> list[int]:
    """Parse a citation group string into a list of ints, handling ranges."""
    numbers: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                numbers.extend(range(int(start), int(end) + 1))
            except ValueError:
                pass
        else:
            with contextlib.suppress(ValueError):
                numbers.append(int(part))
    return numbers


def extract_citation_indices(text: str) -> set[int]:
    """Return all 1-based citation indices found in the text."""
    return {
        number
        for match in _CITATION_RE.findall(text)
        for number in parse_citation_group(match[1:-1])
    }


def rewrite_citations(text: str, renumber_map: dict[int, int]) -> str:
    """Renumber valid citations and strip out-of-range references."""

    def _rewrite(match: re.Match[str]) -> str:
        numbers = parse_citation_group(match.group(0)[1:-1])
        kept = sorted(
            {renumber_map[number] for number in numbers if number in renumber_map}
        )
        return f"[{', '.join(str(number) for number in kept)}]" if kept else ""

    return _CITATION_RE.sub(_rewrite, text)
