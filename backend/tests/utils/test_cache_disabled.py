import pytest

from src.core.config import settings
from src.utils.cache import cache


@pytest.mark.asyncio
async def test_cache_disabled_returns_defaults(monkeypatch):
    monkeypatch.setattr(settings, "CACHE_ENABLED", False)

    assert await cache.get("cache:key") is None
    assert await cache.set("cache:key", {"value": 1}, ttl=5) is False
    assert await cache.delete("cache:key") == 0
    assert await cache.delete_pattern("cache:*") == 0


@pytest.mark.asyncio
async def test_cache_disabled_ignores_existing_client(monkeypatch):
    monkeypatch.setattr(settings, "CACHE_ENABLED", False)
    cache._client = object()

    assert await cache.get("cache:ignored") is None
    assert await cache.set("cache:ignored", {"value": 2}, ttl=5) is False
