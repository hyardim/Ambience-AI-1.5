import asyncio
import json
import logging
from typing import Any, Optional

from redis.asyncio import Redis

from src.core.config import settings

logger = logging.getLogger("backend.cache")


class RedisCache:
    def __init__(self) -> None:
        self._client: Optional[Redis] = None

    async def _get_client(self) -> Optional[Redis]:
        if not settings.CACHE_ENABLED:
            return None
        if self._client is None:
            self._client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._client

    async def get(self, key: str, *, user_id: Optional[int] = None, resource: str = "") -> Optional[Any]:
        client = await self._get_client()
        if client is None:
            logger.debug("cache.disabled", extra={"key": key, "user_id": user_id, "resource": resource})
            return None
        try:
            value = await client.get(key)
            if value is None:
                logger.debug("cache.miss", extra={"key": key, "user_id": user_id, "resource": resource})
                return None
            ttl = await client.ttl(key)
            logger.debug(
                "cache.hit",
                extra={"key": key, "user_id": user_id, "resource": resource, "ttl": ttl},
            )
            return json.loads(value)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "cache.error",
                extra={"key": key, "user_id": user_id, "resource": resource, "error": str(exc)},
            )
            return None

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ttl: int,
        user_id: Optional[int] = None,
        resource: str = "",
    ) -> bool:
        client = await self._get_client()
        if client is None:
            logger.debug("cache.disabled", extra={"key": key, "user_id": user_id, "resource": resource})
            return False
        try:
            payload = json.dumps(value)
            await client.set(key, payload, ex=ttl)
            logger.debug(
                "cache.set",
                extra={"key": key, "user_id": user_id, "resource": resource, "ttl": ttl},
            )
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "cache.error",
                extra={"key": key, "user_id": user_id, "resource": resource, "error": str(exc)},
            )
            return False

    async def delete(self, key: str, *, user_id: Optional[int] = None, resource: str = "") -> int:
        client = await self._get_client()
        if client is None:
            return 0
        try:
            count = await client.delete(key)
            logger.debug(
                "cache.delete",
                extra={"key": key, "user_id": user_id, "resource": resource, "count": count},
            )
            return count
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "cache.error",
                extra={"key": key, "user_id": user_id, "resource": resource, "error": str(exc)},
            )
            return 0

    async def delete_pattern(self, pattern: str, *, user_id: Optional[int] = None, resource: str = "") -> int:
        client = await self._get_client()
        if client is None:
            return 0
        try:
            keys = [key async for key in client.scan_iter(match=pattern)]
            if not keys:
                return 0
            count = await client.delete(*keys)
            logger.debug(
                "cache.invalidate",
                extra={"pattern": pattern, "user_id": user_id, "resource": resource, "count": count},
            )
            return count
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "cache.error",
                extra={"pattern": pattern, "user_id": user_id, "resource": resource, "error": str(exc)},
            )
            return 0

    def get_sync(self, key: str, *, user_id: Optional[int] = None, resource: str = "") -> Optional[Any]:
        return asyncio.run(self.get(key, user_id=user_id, resource=resource))

    def set_sync(
        self,
        key: str,
        value: Any,
        *,
        ttl: int,
        user_id: Optional[int] = None,
        resource: str = "",
    ) -> bool:
        return asyncio.run(self.set(key, value, ttl=ttl, user_id=user_id, resource=resource))

    def delete_sync(self, key: str, *, user_id: Optional[int] = None, resource: str = "") -> int:
        return asyncio.run(self.delete(key, user_id=user_id, resource=resource))

    def delete_pattern_sync(self, pattern: str, *, user_id: Optional[int] = None, resource: str = "") -> int:
        return asyncio.run(self.delete_pattern(pattern, user_id=user_id, resource=resource))


class CacheKeys:
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix.rstrip(":")

    def chat_list(
        self,
        user_id: int,
        page: int,
        page_size: int,
        status: Optional[str] = None,
        specialty: Optional[str] = None,
    ) -> str:
        status_part = status or "all"
        specialty_part = specialty or "all"
        return f"{self._prefix}:user:{user_id}:chats:{status_part}:{specialty_part}:{page}:{page_size}"

    def chat_detail(self, user_id: int, chat_id: int) -> str:
        return f"{self._prefix}:user:{user_id}:chat:{chat_id}"

    def chat_detail_pattern(self, chat_id: int) -> str:
        return f"{self._prefix}:user:*:chat:{chat_id}"

    def chat_list_pattern(self, user_id: int) -> str:
        return f"{self._prefix}:user:{user_id}:chats:*"

    def user_profile(self, user_id: int) -> str:
        return f"{self._prefix}:user:{user_id}:profile"


cache = RedisCache()
cache_keys = CacheKeys(settings.CACHE_KEY_PREFIX)
