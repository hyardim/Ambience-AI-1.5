"""
In-process Server-Sent Events pub/sub for chat AI generation.

Events are keyed by chat_id so every SSE client watching a chat receives
the same generation lifecycle events.  Each subscriber gets its own
asyncio.Queue so back-pressure on one client does not block others.

A short-lived **replay buffer** retains the latest ``stream_start`` and
``content`` events per chat so
that late-connecting clients still receive current state instead of
missing the generation entirely.

Event types
-----------
- stream_start   : AI generation has begun; includes the placeholder message id.
- content        : Partial or full AI content available (cumulative text).
- complete       : Generation finished; final content + citations attached.
- error          : Generation failed; includes an error description.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


@dataclass
class SSEEvent:
    event: str  # stream_start | content | complete | error
    data: dict[str, Any]

    def encode(self) -> str:
        """Format as an SSE text frame."""
        return f"event: {self.event}\ndata: {json.dumps(self.data)}\n\n"


class _ChatEventBus:
    """Global, in-process event bus for chat generation events.

    Supports both async callers (``publish`` / ``close_chat``) and sync
    background threads (``publish_threadsafe`` / ``close_chat_threadsafe``)
    which use the main event loop via ``call_soon_threadsafe``.

    Maintains a per-chat replay buffer so late-connecting SSE clients
    receive the latest accumulated state.
    """

    def __init__(self) -> None:
        # chat_id -> list of subscriber queues
        self._subscribers: dict[int, list[asyncio.Queue[SSEEvent | None]]] = {}
        self._lock = asyncio.Lock()
        # Replay buffer per chat
        self._stream_start: dict[int, SSEEvent] = {}
        self._last_content: dict[int, SSEEvent] = {}
        self._active_streams: set[int] = set()
        # Reference to the main event loop (set on first subscribe)
        self._loop: asyncio.AbstractEventLoop | None = None
        # Thread lock for the threadsafe publish path
        self._thread_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Async API (use from coroutines on the main event loop)
    # ------------------------------------------------------------------

    _MAX_SUBSCRIBER_QUEUE_SIZE = 256

    async def subscribe(self, chat_id: int) -> asyncio.Queue[SSEEvent | None]:
        async with self._lock:
            if self._loop is None:
                self._loop = asyncio.get_running_loop()
            q: asyncio.Queue[SSEEvent | None] = asyncio.Queue(
                maxsize=self._MAX_SUBSCRIBER_QUEUE_SIZE,
            )
            self._subscribers.setdefault(chat_id, []).append(q)
            # Replay buffered events only while a stream is currently active.
            # Completed streams are already persisted in the database; replaying
            # stale terminal events here would close pre-subscribed clients
            # before the next generation starts.
            if chat_id in self._active_streams:
                start = self._stream_start.get(chat_id)
                if start:
                    q.put_nowait(start)
                last = self._last_content.get(chat_id)
                if last:
                    q.put_nowait(last)
            return q

    async def unsubscribe(
        self, chat_id: int, q: asyncio.Queue[SSEEvent | None]
    ) -> None:
        async with self._lock:
            subs = self._subscribers.get(chat_id)
            if subs:
                try:
                    subs.remove(q)
                except ValueError:
                    pass
                if not subs:
                    del self._subscribers[chat_id]
                    if chat_id not in self._active_streams:
                        self._clear_buffer(chat_id)

    async def publish(self, chat_id: int, event: SSEEvent) -> None:
        async with self._lock:
            self._update_buffer(chat_id, event)
            subs = list(self._subscribers.get(chat_id, []))
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Dropping SSE event for chat %s – subscriber queue full", chat_id
                )

    async def close_chat(self, chat_id: int) -> None:
        """Send a sentinel (None) to all subscribers so they can exit cleanly."""
        async with self._lock:
            subs = list(self._subscribers.get(chat_id, []))
            self._clear_buffer(chat_id)
        for q in subs:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    # ------------------------------------------------------------------
    # Thread-safe API (use from background threads)
    # ------------------------------------------------------------------

    def publish_threadsafe(self, chat_id: int, event: SSEEvent) -> None:
        """Publish an event from a background thread.

        Schedules the actual queue operations on the main event loop via
        ``call_soon_threadsafe`` so that asyncio.Queue waiters are woken
        correctly.
        """
        with self._thread_lock:
            self._update_buffer(chat_id, event)
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._sync_put, chat_id, event)
        else:
            # Fallback: direct put (best-effort, may not wake waiters)
            for q in list(self._subscribers.get(chat_id, [])):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    def close_chat_threadsafe(self, chat_id: int) -> None:
        """Thread-safe variant of :meth:`close_chat`."""
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._sync_close, chat_id)
        else:
            for q in list(self._subscribers.get(chat_id, [])):
                try:
                    q.put_nowait(None)
                except asyncio.QueueFull:
                    pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_buffer(self, chat_id: int, event: SSEEvent) -> None:
        """Update the per-chat replay buffer (called under a lock)."""
        if event.event == "stream_start":
            self._active_streams.add(chat_id)
            self._stream_start[chat_id] = event
            self._last_content.pop(chat_id, None)
        elif event.event == "content":
            self._last_content[chat_id] = event
        elif event.event in ("complete", "error"):
            self._active_streams.discard(chat_id)

    def _clear_buffer(self, chat_id: int) -> None:
        """Drop replay state for a chat once streaming is done/closed."""
        self._active_streams.discard(chat_id)
        self._stream_start.pop(chat_id, None)
        self._last_content.pop(chat_id, None)

    def _sync_put(self, chat_id: int, event: SSEEvent) -> None:
        """Put an event into all subscriber queues (runs on the event loop)."""
        for q in list(self._subscribers.get(chat_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Dropping SSE event for chat %s – subscriber queue full", chat_id
                )

    def _sync_close(self, chat_id: int) -> None:
        """Send sentinel to all subscribers (runs on the event loop)."""
        for q in list(self._subscribers.get(chat_id, [])):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
        self._clear_buffer(chat_id)


# Module-level singleton
chat_event_bus = _ChatEventBus()


_SSE_IDLE_TIMEOUT = 300  # seconds — drop idle connections to prevent subscriber leaks


async def sse_event_generator(
    chat_id: int,
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE-formatted strings for a chat.

    Use with ``StreamingResponse(sse_event_generator(chat_id), media_type="text/event-stream")``.

    Includes an idle timeout so that connections dropped without a clean close
    (e.g. network failure) are eventually cleaned up rather than leaking
    subscriber queues indefinitely.
    """
    q = await chat_event_bus.subscribe(chat_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=_SSE_IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                # Send a keep-alive comment to detect dead connections.
                # If the client has disconnected, the write will fail and
                # the generator will be closed, triggering unsubscribe.
                yield ": keep-alive\n\n"
                continue
            if event is None:
                # Sentinel – stream finished
                break
            yield event.encode()
    finally:
        await chat_event_bus.unsubscribe(chat_id, q)
