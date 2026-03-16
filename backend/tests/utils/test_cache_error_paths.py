import pytest
from src.utils.cache import cache


class InvalidJsonRedis:
    async def get(self, _key):
        return "not-json"

    async def ttl(self, _key):
        return 5


class SetErrorRedis:
    async def set(self, _key, _value, ex=None):
        raise RuntimeError("set-failed")


class DeleteErrorRedis:
    async def delete(self, *_keys):
        raise RuntimeError("delete-failed")


class ScanErrorRedis:
    async def scan_iter(self, match=None):
        raise RuntimeError("scan-failed")


@pytest.mark.asyncio
async def test_cache_get_invalid_json_returns_none(monkeypatch):
    async def fake_get_client():
        return InvalidJsonRedis()

    monkeypatch.setattr(cache, "_get_client", fake_get_client)

    assert await cache.get("bad:json") is None


@pytest.mark.asyncio
async def test_cache_set_error_returns_false(monkeypatch):
    async def fake_get_client():
        return SetErrorRedis()

    monkeypatch.setattr(cache, "_get_client", fake_get_client)

    assert await cache.set("key", {"value": 1}, ttl=5) is False


@pytest.mark.asyncio
async def test_cache_delete_error_returns_zero(monkeypatch):
    async def fake_get_client():
        return DeleteErrorRedis()

    monkeypatch.setattr(cache, "_get_client", fake_get_client)

    assert await cache.delete("key") == 0


@pytest.mark.asyncio
async def test_cache_delete_pattern_error_returns_zero(monkeypatch):
    async def fake_get_client():
        return ScanErrorRedis()

    monkeypatch.setattr(cache, "_get_client", fake_get_client)

    assert await cache.delete_pattern("cache:*") == 0
