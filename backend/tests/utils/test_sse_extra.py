from __future__ import annotations

import asyncio

import pytest
from src.utils import sse
from src.utils.sse import SSEEvent, _ChatEventBus


class FullQueue:
    def put_nowait(self, value):
        raise asyncio.QueueFull


class WeirdList(list):
    def remove(self, value):
        raise ValueError


@pytest.mark.asyncio
async def test_publish_logs_when_queue_full(monkeypatch):
    bus = _ChatEventBus()
    bus._subscribers[1] = [FullQueue()]
    warnings = []
    monkeypatch.setattr(sse.logger, "warning", lambda *args: warnings.append(args))

    await bus.publish(1, SSEEvent(event="content", data={"x": 1}))

    assert warnings


@pytest.mark.asyncio
async def test_unsubscribe_ignores_missing_queue():
    bus = _ChatEventBus()
    queue = asyncio.Queue()
    bus._subscribers[1] = WeirdList([queue])
    await bus.unsubscribe(1, queue)
    assert 1 in bus._subscribers


@pytest.mark.asyncio
async def test_close_chat_ignores_full_queue():
    bus = _ChatEventBus()
    bus._subscribers[1] = [FullQueue()]
    await bus.close_chat(1)


def test_publish_threadsafe_fallback_ignores_full_queue():
    bus = _ChatEventBus()
    bus._subscribers[1] = [FullQueue()]
    bus.publish_threadsafe(1, SSEEvent(event="content", data={"x": 1}))
    assert bus._last_content[1].data["x"] == 1


def test_close_chat_threadsafe_fallback_ignores_full_queue():
    bus = _ChatEventBus()
    bus._subscribers[1] = [FullQueue()]
    bus.close_chat_threadsafe(1)


def test_close_chat_threadsafe_uses_loop_callback():
    bus = _ChatEventBus()

    class FakeLoop:
        def is_running(self):
            return True

        def call_soon_threadsafe(self, fn, chat_id):
            fn(chat_id)

    q = asyncio.Queue()
    bus._subscribers[1] = [q]
    bus._loop = FakeLoop()
    bus.close_chat_threadsafe(1)
    assert q.get_nowait() is None


def test_sync_put_logs_when_queue_full(monkeypatch):
    bus = _ChatEventBus()
    bus._subscribers[1] = [FullQueue()]
    warnings = []
    monkeypatch.setattr(sse.logger, "warning", lambda *args: warnings.append(args))
    bus._sync_put(1, SSEEvent(event="content", data={"x": 1}))
    assert warnings


def test_sync_close_ignores_full_queue():
    bus = _ChatEventBus()
    bus._subscribers[1] = [FullQueue()]
    bus._sync_close(1)


@pytest.mark.asyncio
async def test_sse_event_generator_unsubscribes_on_close(monkeypatch):
    queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
    await queue.put(SSEEvent(event="content", data={"hello": "world"}))
    await queue.put(None)
    unsubscribed = []

    async def fake_subscribe(chat_id):
        return queue

    async def fake_unsubscribe(chat_id, q):
        unsubscribed.append((chat_id, q))

    monkeypatch.setattr(sse.chat_event_bus, "subscribe", fake_subscribe)
    monkeypatch.setattr(sse.chat_event_bus, "unsubscribe", fake_unsubscribe)

    frames = []
    async for frame in sse.sse_event_generator(9):
        frames.append(frame)

    assert frames and frames[0].startswith("event: content")
    assert unsubscribed and unsubscribed[0][0] == 9
