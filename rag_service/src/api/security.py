from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException, status

INTERNAL_API_KEY_HEADER = "X-Internal-API-Key"


def _is_development_mode() -> bool:
    """Return True when running in an explicit development/test environment.

    Checks the ``RAG_ENV`` environment variable (falling back to ``ENV``).
    Only ``development`` and ``test`` are considered non-production.
    """
    env = (os.getenv("RAG_ENV") or os.getenv("ENV") or "production").strip().lower()
    return env in ("development", "test")


def require_internal_api_key(
    x_internal_api_key: str | None = Header(
        default=None,
        alias=INTERNAL_API_KEY_HEADER,
    ),
) -> None:
    """Validate the shared internal API key on every request.

    Behaviour:
    * If ``RAG_INTERNAL_API_KEY`` is set to a non-empty value, the request
      header must match it exactly (constant-time comparison).
    * If the env var is **missing or empty** and we are in *development/test*
      mode (``RAG_ENV`` or ``ENV`` equals ``development`` or ``test``), auth
      is bypassed so local workflows keep working.
    * In production with an empty/missing key the endpoint returns **500** to
      prevent silently running without authentication.
    """

    expected_key = os.getenv("RAG_INTERNAL_API_KEY", "").strip()

    if not expected_key:
        if _is_development_mode():
            return
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured",
        )

    if not x_internal_api_key or not secrets.compare_digest(
        x_internal_api_key,
        expected_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )
