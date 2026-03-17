from __future__ import annotations

import re
from functools import lru_cache
from typing import Protocol

import tiktoken

from .logger import setup_logger

logger = setup_logger(__name__)


class _Encoder(Protocol):
    def encode(self, text: str) -> list[int]: ...


_FALLBACK_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@lru_cache(maxsize=1)
def _load_encoder() -> _Encoder | None:
    """Load the preferred tokenizer, falling back offline if unavailable."""
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception as exc:  # pragma: no cover - exercised via public fallback path
        logger.warning(
            "Falling back to regex token counting because "
            f"cl100k_base could not be loaded: {exc}"
        )
        return None


def count_tokens(text: str) -> int:
    """Return a deterministic token count with an offline-safe fallback."""
    encoder = _load_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return len(_FALLBACK_TOKEN_PATTERN.findall(text))
