import asyncio
import atexit
import concurrent.futures
import json
import logging
import threading
from collections.abc import AsyncIterator, Coroutine
from typing import Any, Optional
from urllib.parse import quote_plus

from redis.asyncio import Redis

from src.core.config import settings

logger = logging.getLogger("backend.cache")

# A dedicated event loop on a daemon thread for running async cache
# operations from synchronous (threadpool) contexts.  This avoids the
# ``asyncio.run()`` anti-pattern which creates and tears down a fresh
# event loop per call and fails when an event loop is already running.
_sync_loop: asyncio.AbstractEventLoop | None = None
_sync_thread: threading.Thread | None = None
_sync_loop_lock = threading.Lock()


def _sync_loop_runner(loop: asyncio.AbstractEventLoop, ready: threading.Event) -> None:
    asyncio.set_event_loop(loop)
    ready.set()
    loop.run_forever()


def _stop_sync_loop() -> None:
    global _sync_loop, _sync_thread
    loop = _sync_loop
    if loop is None or loop.is_closed():
        return
    loop.call_soon_threadsafe(loop.stop)
    if _sync_thread is not None and _sync_thread.is_alive():
        _sync_thread.join(timeout=1)
    try:
        loop.close()
    except RuntimeError:
        pass
    _sync_loop = None
    _sync_thread = None


atexit.register(_stop_sync_loop)


def _get_sync_loop() -> asyncio.AbstractEventLoop:
    global _sync_loop, _sync_thread
    if _sync_loop is not None and not _sync_loop.is_closed():
        return _sync_loop
    with _sync_loop_lock:
        if _sync_loop is None or _sync_loop.is_closed():
            _sync_loop = asyncio.new_event_loop()
            ready = threading.Event()
            _sync_thread = threading.Thread(
                target=_sync_loop_runner,
                args=(_sync_loop, ready),
                daemon=True,
            )
            _sync_thread.start()
            ready.wait(timeout=1)
    return _sync_loop


def _run_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from a synchronous context."""
    loop = _get_sync_loop()
    future: concurrent.futures.Future[Any] = asyncio.run_coroutine_threadsafe(
        coro, loop
    )
    try:
        return future.result(timeout=5)
    except Exception:
        future.cancel()
        raise


class RedisCache:
    def __init__(self) -> None:
        self._client: Optional[Redis] = None

    async def _get_client(self) -> Optional[Redis]:
        if not settings.CACHE_ENABLED:
            return None
        if self._client is None:
            self._client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._client

    async def get(
        self, key: str, *, user_id: Optional[int] = None, resource: str = ""
    ) -> Optional[Any]:
        client = await self._get_client()
        if client is None:
            logger.debug(
                "cache.disabled",
                extra={"key": key, "user_id": user_id, "resource": resource},
            )
            return None
        try:
            value = await client.get(key)
            if value is None:
                logger.debug(
                    "cache.miss",
                    extra={"key": key, "user_id": user_id, "resource": resource},
                )
                return None
            ttl = await client.ttl(key)
            logger.debug(
                "cache.hit",
                extra={
                    "key": key,
                    "user_id": user_id,
                    "resource": resource,
                    "ttl": ttl,
                },
            )
            return json.loads(value)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "cache.error",
                extra={
                    "key": key,
                    "user_id": user_id,
                    "resource": resource,
                    "error": str(exc),
                },
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
            logger.debug(
                "cache.disabled",
                extra={"key": key, "user_id": user_id, "resource": resource},
            )
            return False
        try:
            payload = json.dumps(value)
            await client.set(key, payload, ex=ttl)
            logger.debug(
                "cache.set",
                extra={
                    "key": key,
                    "user_id": user_id,
                    "resource": resource,
                    "ttl": ttl,
                },
            )
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "cache.error",
                extra={
                    "key": key,
                    "user_id": user_id,
                    "resource": resource,
                    "error": str(exc),
                },
            )
            return False

    async def delete(
        self, key: str, *, user_id: Optional[int] = None, resource: str = ""
    ) -> int:
        client = await self._get_client()
        if client is None:
            return 0
        try:
            count = await client.delete(key)
            logger.debug(
                "cache.delete",
                extra={
                    "key": key,
                    "user_id": user_id,
                    "resource": resource,
                    "count": count,
                },
            )
            return count
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "cache.error",
                extra={
                    "key": key,
                    "user_id": user_id,
                    "resource": resource,
                    "error": str(exc),
                },
            )
            return 0

    async def delete_pattern(
        self, pattern: str, *, user_id: Optional[int] = None, resource: str = ""
    ) -> int:
        client = await self._get_client()
        if client is None:
            return 0
        try:
            scan_iter = client.scan_iter(match=pattern)
            if isinstance(scan_iter, AsyncIterator):
                keys = [key async for key in scan_iter]
            else:
                keys = list(scan_iter)
            if not keys:
                return 0
            count = await client.delete(*keys)
            logger.debug(
                "cache.invalidate",
                extra={
                    "pattern": pattern,
                    "user_id": user_id,
                    "resource": resource,
                    "count": count,
                },
            )
            return count
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "cache.error",
                extra={
                    "pattern": pattern,
                    "user_id": user_id,
                    "resource": resource,
                    "error": str(exc),
                },
            )
            return 0

    def get_sync(
        self, key: str, *, user_id: Optional[int] = None, resource: str = ""
    ) -> Optional[Any]:
        coro = self.get(key, user_id=user_id, resource=resource)
        try:
            return _run_sync(coro)
        except Exception as exc:  # pragma: no cover - defensive
            coro.close()
            logger.warning(
                "cache.sync_error",
                extra={
                    "operation": "get",
                    "key": key,
                    "user_id": user_id,
                    "resource": resource,
                    "error": str(exc),
                },
            )
            return None

    def set_sync(
        self,
        key: str,
        value: Any,
        *,
        ttl: int,
        user_id: Optional[int] = None,
        resource: str = "",
    ) -> bool:
        coro = self.set(key, value, ttl=ttl, user_id=user_id, resource=resource)
        try:
            return _run_sync(coro)
        except Exception as exc:  # pragma: no cover - defensive
            coro.close()
            logger.warning(
                "cache.sync_error",
                extra={
                    "operation": "set",
                    "key": key,
                    "user_id": user_id,
                    "resource": resource,
                    "error": str(exc),
                },
            )
            return False

    def delete_sync(
        self, key: str, *, user_id: Optional[int] = None, resource: str = ""
    ) -> int:
        coro = self.delete(key, user_id=user_id, resource=resource)
        try:
            return _run_sync(coro)
        except Exception as exc:  # pragma: no cover - defensive
            coro.close()
            logger.warning(
                "cache.sync_error",
                extra={
                    "operation": "delete",
                    "key": key,
                    "user_id": user_id,
                    "resource": resource,
                    "error": str(exc),
                },
            )
            return 0

    def delete_pattern_sync(
        self, pattern: str, *, user_id: Optional[int] = None, resource: str = ""
    ) -> int:
        coro = self.delete_pattern(pattern, user_id=user_id, resource=resource)
        try:
            return _run_sync(coro)
        except Exception as exc:  # pragma: no cover - defensive
            coro.close()
            logger.warning(
                "cache.sync_error",
                extra={
                    "operation": "delete_pattern",
                    "pattern": pattern,
                    "user_id": user_id,
                    "resource": resource,
                    "error": str(exc),
                },
            )
            return 0


# Cache keys include user scoping to avoid cross-tenant leakage.
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

    def specialist_queue(self, specialty: Optional[str] = None) -> str:
        specialty_part = specialty or "all"
        return f"{self._prefix}:specialist:queue:{specialty_part}"

    def specialist_queue_pattern(self) -> str:
        return f"{self._prefix}:specialist:queue:*"

    def specialist_assigned(self, specialist_id: int) -> str:
        return f"{self._prefix}:specialist:{specialist_id}:assigned"

    def specialist_assigned_pattern(self, specialist_id: Optional[int] = None) -> str:
        if specialist_id is None:
            return f"{self._prefix}:specialist:*:assigned"
        return f"{self._prefix}:specialist:{specialist_id}:assigned"

    def admin_stats(self) -> str:
        return f"{self._prefix}:admin:stats"

    def admin_chat_list(
        self,
        *,
        status: Optional[str] = None,
        specialty: Optional[str] = None,
        user_id: Optional[int] = None,
        specialist_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> str:
        return (
            f"{self._prefix}:admin:chats:"
            f"{status or 'all'}:{specialty or 'all'}:{user_id or 'all'}:"
            f"{specialist_id or 'all'}:{skip}:{limit}"
        )

    def admin_chat_list_pattern(self) -> str:
        return f"{self._prefix}:admin:chats:*"

    def admin_chat_detail(self, chat_id: int) -> str:
        return f"{self._prefix}:admin:chat:{chat_id}"

    def admin_chat_detail_pattern(self, chat_id: Optional[int] = None) -> str:
        if chat_id is None:
            return f"{self._prefix}:admin:chat:*"
        return f"{self._prefix}:admin:chat:{chat_id}"

    def admin_audit_logs(
        self,
        *,
        action: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        user_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 200,
    ) -> str:
        return (
            f"{self._prefix}:admin:logs:"
            f"{action or 'all'}:{category or 'all'}:{quote_plus(search or 'all')}:"
            f"{user_id or 'all'}:{date_from or 'all'}:{date_to or 'all'}:{limit}"
        )

    def admin_audit_logs_pattern(self) -> str:
        return f"{self._prefix}:admin:logs:*"

    def notifications(self, user_id: int, *, unread_only: bool = False) -> str:
        state = "unread" if unread_only else "all"
        return f"{self._prefix}:user:{user_id}:notifications:{state}"

    def notifications_pattern(self, user_id: int) -> str:
        return f"{self._prefix}:user:{user_id}:notifications:*"

    def notifications_unread_count(self, user_id: int) -> str:
        return f"{self._prefix}:user:{user_id}:notifications:count:unread"


cache = RedisCache()
cache_keys = CacheKeys(settings.CACHE_KEY_PREFIX)
