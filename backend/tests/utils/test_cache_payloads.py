import pytest

from src.utils.cache import cache


class FakeRedis:
    def __init__(self) -> None:
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def ttl(self, key):
        return 10


@pytest.mark.asyncio
async def test_cache_roundtrip_list_payload(monkeypatch):
    fake = FakeRedis()

    async def fake_get_client():
        return fake

    monkeypatch.setattr(cache, "_get_client", fake_get_client)

    payload = [
        {"id": 1, "title": "Chat A"},
        {"id": 2, "title": "Chat B"},
    ]

    assert await cache.set("cache:list", payload, ttl=30) is True
    assert await cache.get("cache:list") == payload


@pytest.mark.asyncio
async def test_cache_roundtrip_nested_dict(monkeypatch):
    fake = FakeRedis()

    async def fake_get_client():
        return fake

    monkeypatch.setattr(cache, "_get_client", fake_get_client)

    payload = {"chat": {"id": 9, "messages": ["one", "two"]}}

    assert await cache.set("cache:nested", payload, ttl=30) is True
    assert await cache.get("cache:nested") == payload
