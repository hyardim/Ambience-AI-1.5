import pytest

from src.utils import cache as cache_module
from src.utils.cache import cache


def test_get_sync_uses_async_get(monkeypatch):
    async def fake_get(_key, **_kwargs):
        return {"value": 1}

    monkeypatch.setattr(cache, "get", fake_get)

    assert cache.get_sync("cache:key") == {"value": 1}


def test_set_sync_uses_async_set(monkeypatch):
    async def fake_set(_key, _value, **_kwargs):
        return True

    monkeypatch.setattr(cache, "set", fake_set)

    assert cache.set_sync("cache:key", {"value": 1}, ttl=5) is True


def test_delete_sync_uses_async_delete(monkeypatch):
    async def fake_delete(_key, **_kwargs):
        return 1

    monkeypatch.setattr(cache, "delete", fake_delete)

    assert cache.delete_sync("cache:key") == 1


def test_delete_pattern_sync_uses_async_delete_pattern(monkeypatch):
    async def fake_delete_pattern(_pattern, **_kwargs):
        return 2

    monkeypatch.setattr(cache, "delete_pattern", fake_delete_pattern)

    assert cache.delete_pattern_sync("cache:*") == 2


def test_get_sync_returns_none_on_bridge_error(monkeypatch):
    monkeypatch.setattr(
        "src.utils.cache._run_sync",
        lambda _coro: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert cache.get_sync("cache:key") is None


def test_set_sync_returns_false_on_bridge_error(monkeypatch):
    monkeypatch.setattr(
        "src.utils.cache._run_sync",
        lambda _coro: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert cache.set_sync("cache:key", {"value": 1}, ttl=5) is False


def test_delete_sync_returns_zero_on_bridge_error(monkeypatch):
    monkeypatch.setattr(
        "src.utils.cache._run_sync",
        lambda _coro: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert cache.delete_sync("cache:key") == 0


def test_delete_pattern_sync_returns_zero_on_bridge_error(monkeypatch):
    monkeypatch.setattr(
        "src.utils.cache._run_sync",
        lambda _coro: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert cache.delete_pattern_sync("cache:*") == 0


def test_stop_sync_loop_closes_loop_and_clears_globals(monkeypatch):
    class FakeLoop:
        def __init__(self):
            self.closed = False

        def is_closed(self):
            return False

        def call_soon_threadsafe(self, fn):
            fn()

        def stop(self):
            return None

        def close(self):
            self.closed = True

    class FakeThread:
        def is_alive(self):
            return True

        def join(self, timeout):
            return None

    fake_loop = FakeLoop()
    monkeypatch.setattr(cache_module, "_sync_loop", fake_loop)
    monkeypatch.setattr(cache_module, "_sync_thread", FakeThread())

    cache_module._stop_sync_loop()

    assert fake_loop.closed is True
    assert cache_module._sync_loop is None
    assert cache_module._sync_thread is None


def test_stop_sync_loop_returns_when_loop_missing(monkeypatch):
    monkeypatch.setattr(cache_module, "_sync_loop", None)
    monkeypatch.setattr(cache_module, "_sync_thread", None)

    cache_module._stop_sync_loop()

    assert cache_module._sync_loop is None
    assert cache_module._sync_thread is None


def test_stop_sync_loop_returns_when_loop_already_closed(monkeypatch):
    class ClosedLoop:
        def is_closed(self):
            return True

    closed_loop = ClosedLoop()
    monkeypatch.setattr(cache_module, "_sync_loop", closed_loop)
    monkeypatch.setattr(cache_module, "_sync_thread", None)

    cache_module._stop_sync_loop()

    assert cache_module._sync_loop is closed_loop


def test_stop_sync_loop_handles_close_runtime_error(monkeypatch):
    class FakeLoop:
        def is_closed(self):
            return False

        def call_soon_threadsafe(self, fn):
            fn()

        def stop(self):
            return None

        def close(self):
            raise RuntimeError("already running")

    monkeypatch.setattr(cache_module, "_sync_loop", FakeLoop())
    monkeypatch.setattr(cache_module, "_sync_thread", None)

    cache_module._stop_sync_loop()

    assert cache_module._sync_loop is None
    assert cache_module._sync_thread is None


def test_run_sync_cancels_future_on_exception(monkeypatch):
    class FakeFuture:
        def __init__(self):
            self.cancelled = False

        def result(self, timeout):
            raise RuntimeError("sync bridge failure")

        def cancel(self):
            self.cancelled = True

    fake_future = FakeFuture()
    monkeypatch.setattr(cache_module, "_get_sync_loop", lambda: object())
    monkeypatch.setattr(
        cache_module.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, loop: fake_future,
    )

    async def _coro():
        return 1

    coro = _coro()

    with pytest.raises(RuntimeError, match="sync bridge failure"):
        cache_module._run_sync(coro)

    assert fake_future.cancelled is True
    coro.close()
