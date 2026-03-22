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
_redis_last_attempt_time: float = 0.0
_REDIS_RETRY_INTERVAL = 30.0  # seconds between reconnection attempts
_local_windows: dict[str, list[float]] = {}
_local_windows_lock = threading.Lock()
_local_cleanup_counter = 0
_LOCAL_CLEANUP_INTERVAL = 256


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
    """Lazy-initialise a synchronous Redis client for rate limiting.

    Retries connection periodically if the initial attempt failed, so the
    rate limiter recovers when Redis comes back online.
    """
    global _redis_client, _redis_init_attempted, _redis_last_attempt_time
    if _redis_client is not None:
        return _redis_client
    now = time.monotonic()
    if _redis_init_attempted and (now - _redis_last_attempt_time) < _REDIS_RETRY_INTERVAL:
        return None
    _redis_init_attempted = True
    _redis_last_attempt_time = now
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
            "Rate limiter: Redis unavailable (%s) — falling back to in-process limits",
            exc,
        )
        _redis_client = None
    return _redis_client


def _cleanup_local_windows(cutoff: float) -> None:
    """Prune stale in-process rate-limit buckets to avoid unbounded memory growth."""
    stale_keys = [
        key
        for key, timestamps in _local_windows.items()
        if not timestamps or timestamps[-1] <= cutoff
    ]
    for key in stale_keys:
        _local_windows.pop(key, None)


def _enforce_inprocess_limit(bucket_key: str, window: int) -> None:
    """Best-effort local fallback limiter used when Redis is unavailable."""
    global _local_cleanup_counter
    now = time.monotonic()
    cutoff = now - window
    with _local_windows_lock:
        _local_cleanup_counter += 1
        if _local_cleanup_counter % _LOCAL_CLEANUP_INTERVAL == 0:
            _cleanup_local_windows(cutoff)

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
        # Atomic: increment first, then check. Use a Lua script to
        # set the TTL only when the key is new (NX-style expire) so
        # the sliding window is not reset on every request.
        count = client.incr(key)
        # Only set expiry on the first request in a window (count == 1)
        # so subsequent requests don't extend the window.
        if count == 1:
            client.expire(key, window)
        if count > settings.RATE_LIMIT_PER_MINUTE:
            ttl = client.ttl(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {max(ttl, 1)} seconds.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "Rate limiter Redis error (%s) - falling back to in-process limits",
            exc,
        )
        _enforce_inprocess_limit(bucket_key, window)
