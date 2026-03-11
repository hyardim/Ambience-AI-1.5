"""
In-process Server-Sent Events pub/sub for chat AI generation.

Events are keyed by chat_id so every SSE client watching a chat receives
the same generation lifecycle events.  Each subscriber gets its own
asyncio.Queue so back-pressure on one client does not block others.

Event types
-----------
- stream_start   : AI generation has begun; includes the placeholder message id.
- content        : Partial or full AI content available (when rag_service does
                   not stream, a single content event carries the whole answer).
- complete       : Generation finished; final content + citations attached.
- error          : Generation failed; includes an error description.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
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
    """Global, in-process event bus for chat generation events."""

    def __init__(self) -> None:
        # chat_id -> list of subscriber queues
        self._subscribers: dict[int, list[asyncio.Queue[SSEEvent | None]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, chat_id: int) -> asyncio.Queue[SSEEvent | None]:
        async with self._lock:
            q: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
            self._subscribers.setdefault(chat_id, []).append(q)
            return q

    async def unsubscribe(self, chat_id: int, q: asyncio.Queue[SSEEvent | None]) -> None:
        async with self._lock:
            subs = self._subscribers.get(chat_id)
            if subs:
                try:
                    subs.remove(q)
                except ValueError:
                    pass
                if not subs:
                    del self._subscribers[chat_id]

    async def publish(self, chat_id: int, event: SSEEvent) -> None:
        async with self._lock:
            subs = list(self._subscribers.get(chat_id, []))
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Dropping SSE event for chat %s – subscriber queue full", chat_id)

    async def close_chat(self, chat_id: int) -> None:
        """Send a sentinel (None) to all subscribers so they can exit cleanly."""
        async with self._lock:
            subs = list(self._subscribers.get(chat_id, []))
        for q in subs:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass


# Module-level singleton
chat_event_bus = _ChatEventBus()


async def sse_event_generator(
    chat_id: int,
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE-formatted strings for a chat.

    Use with ``StreamingResponse(sse_event_generator(chat_id), media_type="text/event-stream")``.
    """
    q = await chat_event_bus.subscribe(chat_id)
    try:
        while True:
            event = await q.get()
            if event is None:
                # Sentinel – stream finished
                break
            yield event.encode()
    finally:
        await chat_event_bus.unsubscribe(chat_id, q)
