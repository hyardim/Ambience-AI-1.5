"""Simple sliding-window rate limiter backed by Redis.

When Redis is unavailable, enforcement falls back to in-process limits to
avoid a fail-open posture during cache outages.
"""

import hashlib
import logging
import threading
import time

from fastapi import HTTPException, Request, status

from src.core.config import settings

logger = logging.getLogger(__name__)

_redis_client = None
_redis_init_attempted = False
_local_windows: dict[str, list[float]] = {}
_local_windows_lock = threading.Lock()


def _request_subject(request: Request) -> str:
    """Derive a stable subject bucket from auth artifacts when available."""
    headers = getattr(request, "headers", {})
    cookies = getattr(request, "cookies", {})
    auth = headers.get("authorization") if hasattr(headers, "get") else ""
    auth = auth or ""
    token: str | None = None
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    elif settings.ACCESS_COOKIE_NAME in cookies:
        token = cookies.get(settings.ACCESS_COOKIE_NAME)

    if not token:
        return "anon"

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"session:{token_hash}"


def _get_redis():
    """Lazy-initialise a synchronous Redis client for rate limiting."""
    global _redis_client, _redis_init_attempted
    if _redis_init_attempted:
        return _redis_client
    _redis_init_attempted = True
    if not settings.CACHE_ENABLED:
        return None
    try:
        import redis

        _redis_client = redis.Redis.from_url(
            settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2
        )
        _redis_client.ping()
    except Exception as exc:
        logger.warning(
            "Rate limiter: Redis unavailable (%s) — rate limiting disabled", exc
        )
        _redis_client = None
    return _redis_client


def _enforce_inprocess_limit(bucket_key: str, window: int) -> None:
    """Best-effort local fallback limiter used when Redis is unavailable."""
    now = time.monotonic()
    cutoff = now - window
    with _local_windows_lock:
        window_hits = _local_windows.setdefault(bucket_key, [])
        window_hits[:] = [ts for ts in window_hits if ts > cutoff]
        if len(window_hits) >= settings.RATE_LIMIT_PER_MINUTE:
            retry_after = max(1, int(window - (now - window_hits[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(f"Rate limit exceeded. Try again in {retry_after} seconds."),
            )
        window_hits.append(now)


async def rate_limit_dependency(request: Request) -> None:
    """FastAPI dependency that enforces per session+IP (or anon+IP) rate limits.

    Uses a sliding window counter stored in Redis.  Each IP gets
    ``settings.RATE_LIMIT_PER_MINUTE`` requests per 60-second window.
    """
    client_ip = request.client.host if request.client else "unknown"
    subject = _request_subject(request)
    bucket_key = f"{subject}:{client_ip}"
    window = 60  # seconds
    client = _get_redis()
    if client is None:
        _enforce_inprocess_limit(bucket_key, window)
        return

    key = f"ratelimit:{bucket_key}"

    try:
        current = client.get(key)
        if current is not None and int(current) >= settings.RATE_LIMIT_PER_MINUTE:
            ttl = client.ttl(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {max(ttl, 1)} seconds.",
            )
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        pipe.execute()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "Rate limiter Redis error (%s) - falling back to in-process limits",
            exc,
        )
        _enforce_inprocess_limit(bucket_key, window)
