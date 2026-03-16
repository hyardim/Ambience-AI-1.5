"""Simple sliding-window rate limiter backed by Redis.

Falls back to no-op when Redis is unavailable so the app degrades
gracefully (the rate limiter is a best-effort protection, not a
hard gate).
"""

import logging

from fastapi import HTTPException, Request, status

from src.core.config import settings

logger = logging.getLogger(__name__)

_redis_client = None
_redis_init_attempted = False


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


async def rate_limit_dependency(request: Request) -> None:
    """FastAPI dependency that enforces per-IP rate limiting.

    Uses a sliding window counter stored in Redis.  Each IP gets
    ``settings.RATE_LIMIT_PER_MINUTE`` requests per 60-second window.
    """
    client = _get_redis()
    if client is None:
        return  # Redis not available — skip rate limiting

    client_ip = request.client.host if request.client else "unknown"
    key = f"ratelimit:{client_ip}"
    window = 60  # seconds

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
        # Redis failure should not break the request — degrade gracefully
        logger.debug("Rate limiter error: %s", exc)
