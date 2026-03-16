from __future__ import annotations

from src.services.cache_invalidation import (
    invalidate_admin_chat_caches_sync,
    invalidate_admin_stats_sync,
    invalidate_specialist_lists_sync,
)


def _invalidate_specialist_lists(
    *,
    specialty: str | None = None,
    specialist_id: int | None = None,
) -> None:
    invalidate_specialist_lists_sync(
        specialty=specialty,
        specialist_id=specialist_id,
    )


def _invalidate_admin_stats_cache() -> None:
    invalidate_admin_stats_sync()


def _invalidate_admin_chat_caches(chat_id: int | None = None) -> None:
    invalidate_admin_chat_caches_sync(chat_id)


def _build_manual_citations(sources: list[str] | None) -> list[dict] | None:
    if not sources:
        return None

    cleaned = [
        source.strip()
        for source in sources
        if isinstance(source, str) and source.strip()
    ]
    if not cleaned:
        return None

    return [
        {
            "title": source,
            "source_name": "Manual source",
            "metadata": {
                "title": source,
                "source_name": "Manual source",
            },
        }
        for source in cleaned
    ]
