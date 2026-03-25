import fnmatch

import pytest

from src.utils.cache import cache


class FakeRedis:
    def __init__(self) -> None:
        self.store = {}

    async def delete(self, *keys):
        count = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                count += 1
        return count

    async def scan_iter(self, match=None):
        for key in list(self.store.keys()):
            if match is None or fnmatch.fnmatch(key, match):
                yield key


@pytest.mark.asyncio
async def test_delete_pattern_removes_only_matching_keys(monkeypatch):
    fake = FakeRedis()
    fake.store = {
        "cache:user:1:chat:1": "a",
        "cache:user:2:chat:1": "b",
        "cache:user:1:profile": "c",
        "other:prefix": "d",
    }

    async def fake_get_client():
        return fake

    monkeypatch.setattr(cache, "_get_client", fake_get_client)

    deleted = await cache.delete_pattern("cache:user:*:chat:1")
    assert deleted == 2
    assert "cache:user:1:profile" in fake.store
    assert "other:prefix" in fake.store


@pytest.mark.asyncio
async def test_delete_pattern_no_matches_returns_zero(monkeypatch):
    fake = FakeRedis()
    fake.store = {"cache:user:1:profile": "c"}

    async def fake_get_client():
        return fake

    monkeypatch.setattr(cache, "_get_client", fake_get_client)

    deleted = await cache.delete_pattern("cache:user:*:chat:999")
    assert deleted == 0
