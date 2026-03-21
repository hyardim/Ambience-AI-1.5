from __future__ import annotations

from src.core.config import settings


def build_rag_headers(*, idempotency_key: str | None = None) -> dict[str, str]:
    """Build headers for backend -> RAG service calls.

    Adds the internal service key when configured, and optionally forwards
    idempotency for endpoints that support retries.
    """

    headers: dict[str, str] = {}
    if settings.RAG_INTERNAL_API_KEY:
        headers["X-Internal-API-Key"] = settings.RAG_INTERNAL_API_KEY
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers
