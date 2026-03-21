from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException, status

INTERNAL_API_KEY_HEADER = "X-Internal-API-Key"


def require_internal_api_key(
    x_internal_api_key: str | None = Header(
        default=None,
        alias=INTERNAL_API_KEY_HEADER,
    ),
) -> None:
    """Require a shared internal API key when configured.

    The check is enabled when `RAG_INTERNAL_API_KEY` is set to a non-empty value.
    This keeps local/unit test workflows working unless they opt into auth.
    """

    expected_key = os.getenv("RAG_INTERNAL_API_KEY", "").strip()
    if not expected_key:
        return

    if not x_internal_api_key or not secrets.compare_digest(
        x_internal_api_key,
        expected_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )
