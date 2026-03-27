from __future__ import annotations

import re
from typing import Union

from src.schemas.chat import SourceEntry

_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _build_manual_citations(
    sources: list[Union[str, SourceEntry]] | None,
) -> list[dict] | None:
    """Convert specialist-provided source entries into storable citation dicts.

    Each entry may be:
    * a plain string  – the source display name (legacy format)
    * a ``SourceEntry`` – an object with ``name`` and an optional ``url``

    When a plain-string source looks like an HTTP URL it is stored as both
    the ``title`` (display label) **and** the ``source_url`` so that the
    frontend can render it as a clickable link.
    """
    if not sources:
        return None

    citations: list[dict] = []
    for raw in sources:
        if isinstance(raw, SourceEntry):
            name = (raw.name or "").strip()
            url = (raw.url or "").strip() or None
        elif isinstance(raw, str):
            name = raw.strip()
            url = name if _HTTP_URL_RE.match(name) else None
        else:
            continue

        if not name:
            continue

        citation: dict = {
            "title": name,
            "source_name": "Manual source",
            "metadata": {
                "title": name,
                "source_name": "Manual source",
            },
        }
        if url:
            citation["source_url"] = url
            citation["metadata"]["source_url"] = url

        citations.append(citation)

    return citations if citations else None
