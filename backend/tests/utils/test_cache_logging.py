import pytest
from src.core.config import settings
from src.utils.cache import cache


class FakeRedis:
    async def get(self, _key):
        return None


@pytest.mark.asyncio
async def test_cache_logs_miss(monkeypatch, caplog):
    async def fake_get_client():
        return FakeRedis()

    monkeypatch.setattr(cache, "_get_client", fake_get_client)

    with caplog.at_level("DEBUG", logger="backend.cache"):
        assert await cache.get("cache:missing") is None

    assert any(record.message == "cache.miss" for record in caplog.records)


@pytest.mark.asyncio
async def test_cache_logs_disabled(monkeypatch, caplog):
    monkeypatch.setattr(settings, "CACHE_ENABLED", False)

    with caplog.at_level("DEBUG", logger="backend.cache"):
        assert await cache.get("cache:disabled") is None

    assert any(record.message == "cache.disabled" for record in caplog.records)
