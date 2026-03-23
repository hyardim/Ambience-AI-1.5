from __future__ import annotations

import asyncio
import time

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


@pytest.mark.asyncio
async def test_subscribe_replays_start_and_latest_content_during_active_stream():
    bus = _ChatEventBus()
    await bus.publish(7, SSEEvent(event="stream_start", data={"message_id": 1}))
    await bus.publish(7, SSEEvent(event="content", data={"content": "hel"}))
    await bus.publish(7, SSEEvent(event="content", data={"content": "hello"}))

    q = await bus.subscribe(7)
    first = q.get_nowait()
    second = q.get_nowait()

    assert first.event == "stream_start"
    assert second.event == "content"
    assert second.data["content"] == "hello"


@pytest.mark.asyncio
async def test_subscribe_does_not_replay_stale_events_after_stream_terminal():
    bus = _ChatEventBus()
    await bus.publish(3, SSEEvent(event="stream_start", data={"message_id": 2}))
    await bus.publish(3, SSEEvent(event="content", data={"content": "draft"}))
    await bus.publish(3, SSEEvent(event="complete", data={"content": "final"}))

    q = await bus.subscribe(3)

    assert q.empty()


@pytest.mark.asyncio
async def test_close_chat_clears_replay_state():
    bus = _ChatEventBus()
    await bus.publish(21, SSEEvent(event="stream_start", data={"message_id": 11}))
    await bus.publish(21, SSEEvent(event="content", data={"content": "hello"}))

    assert 21 in bus._stream_start
    assert 21 in bus._last_content

    await bus.close_chat(21)

    assert 21 not in bus._stream_start
    assert 21 not in bus._last_content
    assert 21 not in bus._active_streams


@pytest.mark.asyncio
async def test_unsubscribe_clears_terminal_replay_state_when_no_subscribers():
    bus = _ChatEventBus()
    q = await bus.subscribe(22)
    await bus.publish(22, SSEEvent(event="stream_start", data={"message_id": 11}))
    await bus.publish(22, SSEEvent(event="content", data={"content": "hello"}))
    await bus.publish(22, SSEEvent(event="complete", data={"content": "final"}))

    await bus.unsubscribe(22, q)

    assert 22 not in bus._stream_start
    assert 22 not in bus._last_content
    assert 22 not in bus._active_streams


def test_cleanup_expired_buffers_removes_only_inactive_expired_entries():
    bus = _ChatEventBus()
    stale_time = time.monotonic() - (sse._REPLAY_BUFFER_TTL_SECONDS + 10)
    active_time = time.monotonic()
    bus._stream_start[1] = SSEEvent(
        event="stream_start",
        data={"message_id": 1},
        created_at=stale_time,
    )
    bus._last_content[1] = SSEEvent(
        event="content",
        data={"content": "stale"},
        created_at=stale_time,
    )
    bus._stream_start[2] = SSEEvent(
        event="stream_start",
        data={"message_id": 2},
        created_at=active_time,
    )
    bus._last_content[2] = SSEEvent(
        event="content",
        data={"content": "active"},
        created_at=active_time,
    )
    bus._active_streams.add(2)

    bus._cleanup_expired_buffers()

    assert 1 not in bus._stream_start
    assert 1 not in bus._last_content
    assert 2 in bus._stream_start
    assert 2 in bus._last_content


def test_cleanup_expired_buffers_enforces_max_size_for_inactive_entries(monkeypatch):
    bus = _ChatEventBus()
    monkeypatch.setattr(sse, "_REPLAY_BUFFER_MAX_SIZE", 1)
    old_time = time.monotonic() - 100
    new_time = time.monotonic()
    bus._stream_start[1] = SSEEvent(
        event="stream_start",
        data={"message_id": 1},
        created_at=old_time,
    )
    bus._last_content[1] = SSEEvent(
        event="content",
        data={"content": "first"},
        created_at=old_time,
    )
    bus._stream_start[2] = SSEEvent(
        event="stream_start",
        data={"message_id": 2},
        created_at=new_time,
    )
    bus._last_content[2] = SSEEvent(
        event="content",
        data={"content": "second"},
        created_at=new_time,
    )

    bus._cleanup_expired_buffers()

    assert 1 not in bus._stream_start
    assert 2 in bus._stream_start


@pytest.mark.asyncio
async def test_sse_event_generator_emits_keep_alive_on_idle_timeout(monkeypatch):
    queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
    await queue.put(None)
    unsubscribed = []
    call_count = 0
    original_wait_for = sse.asyncio.wait_for

    async def fake_subscribe(chat_id):
        return queue

    async def fake_unsubscribe(chat_id, q):
        unsubscribed.append((chat_id, q))

    async def fake_wait_for(awaitable, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            awaitable.close()
            raise asyncio.TimeoutError
        return await original_wait_for(awaitable, timeout)

    monkeypatch.setattr(sse.chat_event_bus, "subscribe", fake_subscribe)
    monkeypatch.setattr(sse.chat_event_bus, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(sse.asyncio, "wait_for", fake_wait_for)

    frames = []
    async for frame in sse.sse_event_generator(15):
        frames.append(frame)

    assert frames == [": keep-alive\n\n"]
    assert unsubscribed and unsubscribed[0][0] == 15
