import fnmatch

import pytest

from src.utils.cache import cache


class FakeRedis:
    def __init__(self) -> None:
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, *keys):
        count = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                count += 1
        return count

    async def ttl(self, key):
        return 10

    async def scan_iter(self, match=None):
        for key in list(self.store.keys()):
            if match is None or fnmatch.fnmatch(key, match):
                yield key


class ErrorRedis:
    async def get(self, _key):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_cache_set_get_delete_pattern(monkeypatch):
    fake = FakeRedis()

    async def fake_get_client():
        return fake

    monkeypatch.setattr(cache, "_get_client", fake_get_client)

    assert await cache.set("test:key", {"value": 1}, ttl=5)
    assert await cache.get("test:key") == {"value": 1}
    assert await cache.delete_pattern("test:*") == 1
    assert await cache.get("test:key") is None


@pytest.mark.asyncio
async def test_cache_get_error_returns_none(monkeypatch):
    error_client = ErrorRedis()

    async def fake_get_client():
        return error_client

    monkeypatch.setattr(cache, "_get_client", fake_get_client)

    assert await cache.get("oops") is None
