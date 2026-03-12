import pytest

from src.utils.cache import cache


@pytest.mark.asyncio
async def test_get_sync_uses_async_get(monkeypatch):
    async def fake_get(_key, **_kwargs):
        return {"value": 1}

    monkeypatch.setattr(cache, "get", fake_get)

    assert cache.get_sync("cache:key") == {"value": 1}


@pytest.mark.asyncio
async def test_set_sync_uses_async_set(monkeypatch):
    async def fake_set(_key, _value, **_kwargs):
        return True

    monkeypatch.setattr(cache, "set", fake_set)

    assert cache.set_sync("cache:key", {"value": 1}, ttl=5) is True


@pytest.mark.asyncio
async def test_delete_sync_uses_async_delete(monkeypatch):
    async def fake_delete(_key, **_kwargs):
        return 1

    monkeypatch.setattr(cache, "delete", fake_delete)

    assert cache.delete_sync("cache:key") == 1


@pytest.mark.asyncio
async def test_delete_pattern_sync_uses_async_delete_pattern(monkeypatch):
    async def fake_delete_pattern(_pattern, **_kwargs):
        return 2

    monkeypatch.setattr(cache, "delete_pattern", fake_delete_pattern)

    assert cache.delete_pattern_sync("cache:*") == 2
