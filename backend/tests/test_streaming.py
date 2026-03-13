"""
Tests for the SSE streaming infrastructure and the /chats/{id}/stream endpoint.

Covers:
- Event bus publish / subscribe / unsubscribe lifecycle
- SSE event encoding
- Event ordering (stream_start → content → complete)
- The /chats/{id}/stream endpoint auth & access control
- Fallback: the chat still works through polling after streaming finishes
"""

import asyncio
import json

import pytest

from src.utils.sse import SSEEvent, _ChatEventBus, chat_event_bus


# ---------------------------------------------------------------------------
# Unit: SSEEvent encoding
# ---------------------------------------------------------------------------

class TestSSEEvent:

    def test_encode_produces_valid_sse_frame(self):
        ev = SSEEvent(event="content", data={"chat_id": 1, "message_id": 5, "content": "hello"})
        encoded = ev.encode()
        assert encoded.startswith("event: content\n")
        assert "data: " in encoded
        payload = json.loads(encoded.split("data: ", 1)[1].strip())
        assert payload["message_id"] == 5
        assert payload["content"] == "hello"

    def test_encode_ends_with_double_newline(self):
        ev = SSEEvent(event="complete", data={"ok": True})
        assert ev.encode().endswith("\n\n")


# ---------------------------------------------------------------------------
# Unit: ChatEventBus
# ---------------------------------------------------------------------------

class TestChatEventBus:

    @pytest.fixture()
    def bus(self):
        return _ChatEventBus()

    @pytest.mark.asyncio
    async def test_subscribe_and_receive(self, bus):
        q = await bus.subscribe(1)
        ev = SSEEvent(event="stream_start", data={"chat_id": 1, "message_id": 10})
        await bus.publish(1, ev)
        received = q.get_nowait()
        assert received.event == "stream_start"
        assert received.data["message_id"] == 10

    @pytest.mark.asyncio
    async def test_multiple_subscribers_receive(self, bus):
        q1 = await bus.subscribe(1)
        q2 = await bus.subscribe(1)
        ev = SSEEvent(event="content", data={"msg": "hi"})
        await bus.publish(1, ev)
        assert q1.get_nowait().data["msg"] == "hi"
        assert q2.get_nowait().data["msg"] == "hi"

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_queue(self, bus):
        q = await bus.subscribe(1)
        await bus.unsubscribe(1, q)
        # Publishing should not put anything in the removed queue
        await bus.publish(1, SSEEvent(event="content", data={}))
        assert q.empty()

    @pytest.mark.asyncio
    async def test_close_chat_sends_sentinel(self, bus):
        q = await bus.subscribe(42)
        await bus.close_chat(42)
        sentinel = q.get_nowait()
        assert sentinel is None

    @pytest.mark.asyncio
    async def test_publish_to_different_chat_isolated(self, bus):
        q1 = await bus.subscribe(1)
        q2 = await bus.subscribe(2)
        await bus.publish(1, SSEEvent(event="content", data={"for": 1}))
        assert not q2.empty() is False or q2.qsize() == 0
        assert q1.get_nowait().data["for"] == 1
        assert q2.empty()

    @pytest.mark.asyncio
    async def test_event_ordering(self, bus):
        """Events arrive in the order they were published."""
        q = await bus.subscribe(1)
        events = ["stream_start", "content", "complete"]
        for e in events:
            await bus.publish(1, SSEEvent(event=e, data={"step": e}))
        for expected in events:
            received = q.get_nowait()
            assert received.event == expected


# ---------------------------------------------------------------------------
# Integration: /chats/{id}/stream endpoint
# ---------------------------------------------------------------------------

class TestStreamEndpoint:

    def test_stream_requires_token(self, client, created_chat):
        resp = client.get(f"/chats/{created_chat['id']}/stream")
        assert resp.status_code == 422  # missing required query param

    def test_stream_rejects_bad_token(self, client, created_chat):
        resp = client.get(f"/chats/{created_chat['id']}/stream?token=bad.jwt.token")
        assert resp.status_code == 401

    def test_stream_rejects_other_users_chat(
        self, client, created_chat, registered_second_gp
    ):
        other_token = registered_second_gp["access_token"]
        resp = client.get(
            f"/chats/{created_chat['id']}/stream?token={other_token}"
        )
        assert resp.status_code == 404

    def test_stream_nonexistent_chat_returns_404(self, client, registered_gp):
        token = registered_gp["access_token"]
        resp = client.get(f"/chats/99999/stream?token={token}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration: send_message emits SSE events (SQLite inline mode)
# ---------------------------------------------------------------------------

class TestStreamingWithSendMessage:
    """Under SQLite the async AI generation runs inline, so after
    send_message returns, the events have already been published and
    the bus closed.  We verify that the final persisted state is correct
    (placeholder message finalised with is_generating=False)."""

    def test_ai_message_persisted_after_send(self, client, gp_headers, created_chat):
        chat_id = created_chat["id"]
        client.post(
            f"/chats/{chat_id}/message",
            json={"role": "user", "content": "What is lupus?"},
            headers=gp_headers,
        )
        chat_resp = client.get(f"/chats/{chat_id}", headers=gp_headers)
        messages = chat_resp.json()["messages"]
        ai_messages = [m for m in messages if m["sender"] == "ai"]
        assert len(ai_messages) == 1
        assert ai_messages[0]["is_generating"] is False
        assert len(ai_messages[0]["content"]) > 0

    def test_multiple_messages_do_not_duplicate_ai_replies(
        self, client, gp_headers, created_chat
    ):
        chat_id = created_chat["id"]
        for i in range(2):
            client.post(
                f"/chats/{chat_id}/message",
                json={"role": "user", "content": f"Question {i}"},
                headers=gp_headers,
            )
        chat_resp = client.get(f"/chats/{chat_id}", headers=gp_headers)
        messages = chat_resp.json()["messages"]
        ai_messages = [m for m in messages if m["sender"] == "ai"]
        user_messages = [m for m in messages if m["sender"] == "user"]
        # Each user message should have exactly one AI reply
        assert len(ai_messages) == len(user_messages)


# ---------------------------------------------------------------------------
# Unit: Replay buffer for late subscribers
# ---------------------------------------------------------------------------

class TestReplayBuffer:

    @pytest.fixture()
    def bus(self):
        return _ChatEventBus()

    @pytest.mark.asyncio
    async def test_stream_start_buffered(self, bus):
        """stream_start should be replayed to late subscribers."""
        ev = SSEEvent(event="stream_start", data={"chat_id": 1, "message_id": 10})
        await bus.publish(1, ev)
        # Late subscriber
        q = await bus.subscribe(1)
        replayed = q.get_nowait()
        assert replayed.event == "stream_start"
        assert replayed.data["message_id"] == 10

    @pytest.mark.asyncio
    async def test_latest_content_buffered(self, bus):
        """Only the latest content event is replayed."""
        await bus.publish(1, SSEEvent(event="stream_start", data={"chat_id": 1, "message_id": 5}))
        await bus.publish(1, SSEEvent(event="content", data={"content": "A"}))
        await bus.publish(1, SSEEvent(event="content", data={"content": "AB"}))
        await bus.publish(1, SSEEvent(event="content", data={"content": "ABC"}))
        # Late subscriber
        q = await bus.subscribe(1)
        start = q.get_nowait()
        assert start.event == "stream_start"
        content = q.get_nowait()
        assert content.event == "content"
        assert content.data["content"] == "ABC"  # latest only

    @pytest.mark.asyncio
    async def test_terminal_event_replayed_with_sentinel(self, bus):
        """Completed streams should not be replayed to future subscribers."""
        await bus.publish(1, SSEEvent(event="stream_start", data={"chat_id": 1, "message_id": 5}))
        await bus.publish(1, SSEEvent(event="content", data={"content": "final"}))
        await bus.publish(1, SSEEvent(event="complete", data={"content": "final", "citations": []}))
        # Late subscriber after completion
        q = await bus.subscribe(1)
        assert q.empty()

    @pytest.mark.asyncio
    async def test_buffer_cleared_on_new_stream_start(self, bus):
        """A new stream_start clears stale buffer from previous generation."""
        await bus.publish(1, SSEEvent(event="stream_start", data={"message_id": 1}))
        await bus.publish(1, SSEEvent(event="content", data={"content": "old"}))
        await bus.publish(1, SSEEvent(event="complete", data={"content": "old"}))
        # New generation
        await bus.publish(1, SSEEvent(event="stream_start", data={"message_id": 2}))
        q = await bus.subscribe(1)
        start = q.get_nowait()
        assert start.data["message_id"] == 2
        assert q.empty()  # old content/complete should be cleared


# ---------------------------------------------------------------------------
# Unit: Thread-safe publish
# ---------------------------------------------------------------------------

class TestThreadSafePublish:

    @pytest.fixture()
    def bus(self):
        return _ChatEventBus()

    @pytest.mark.asyncio
    async def test_publish_threadsafe_updates_buffer(self, bus):
        """publish_threadsafe should update the replay buffer."""
        # Subscribe first to set the loop reference
        q = await bus.subscribe(1)
        ev = SSEEvent(event="stream_start", data={"chat_id": 1, "message_id": 7})
        bus.publish_threadsafe(1, ev)
        # Give the event loop a chance to process call_soon_threadsafe
        await asyncio.sleep(0.05)
        assert not q.empty()
        received = q.get_nowait()
        assert received.event == "stream_start"
        assert received.data["message_id"] == 7


# ---------------------------------------------------------------------------
# Integration: Multi-content event ordering (cumulative streaming)
# ---------------------------------------------------------------------------

class TestMultiContentEventOrdering:

    @pytest.fixture()
    def bus(self):
        return _ChatEventBus()

    @pytest.mark.asyncio
    async def test_content_events_arrive_in_order(self, bus):
        """Multiple content events should arrive in publish order."""
        q = await bus.subscribe(1)
        contents = ["H", "He", "Hel", "Hell", "Hello"]
        await bus.publish(1, SSEEvent(event="stream_start", data={"message_id": 1}))
        for c in contents:
            await bus.publish(1, SSEEvent(event="content", data={"content": c}))
        await bus.publish(1, SSEEvent(event="complete", data={"content": "Hello"}))

        received = []
        while not q.empty():
            ev = q.get_nowait()
            if ev is not None:
                received.append(ev)

        assert received[0].event == "stream_start"
        content_events = [e for e in received if e.event == "content"]
        assert len(content_events) == len(contents)
        for i, ev in enumerate(content_events):
            assert ev.data["content"] == contents[i]
        assert received[-1].event == "complete"


# ---------------------------------------------------------------------------
# Integration: Specialist stream authorization
# ---------------------------------------------------------------------------

class TestSpecialistStreamAuthorization:

    def test_specialist_can_access_submitted_queue_chat_stream(
        self, client, submitted_chat, registered_specialist,
    ):
        from unittest.mock import patch

        token = registered_specialist["access_token"]
        chat_id = submitted_chat["id"]

        async def _one_event(_: int):
            yield "event: stream_start\ndata: {}\n\n"

        with patch("src.api.chats.sse_event_generator", side_effect=_one_event):
            resp = client.get(f"/chats/{chat_id}/stream?token={token}")
            assert resp.status_code == 200

    def test_specialist_can_access_assigned_chat_stream(
        self, client, submitted_chat, registered_specialist, specialist_headers,
    ):
        from unittest.mock import patch

        chat_id = submitted_chat["id"]
        specialist_id = registered_specialist["user"]["id"]
        # Assign the specialist
        client.post(
            f"/specialist/chats/{chat_id}/assign",
            json={"specialist_id": specialist_id},
            headers=specialist_headers,
        )
        # Specialist should be able to access the stream endpoint
        token = registered_specialist["access_token"]
        async def _one_event(_: int):
            yield "event: stream_start\ndata: {}\n\n"

        with patch("src.api.chats.sse_event_generator", side_effect=_one_event):
            resp = client.get(f"/chats/{chat_id}/stream?token={token}")
            # Should not be 404 – should be 200 (SSE stream)
            assert resp.status_code == 200

    def test_specialist_cannot_access_outside_specialty_stream(
        self, client, gp_headers, registered_specialist,
    ):
        cardio = client.post(
            "/chats/", json={"title": "Cardio Chat", "specialty": "cardiology"}, headers=gp_headers
        ).json()
        client.post(
            f"/chats/{cardio['id']}/message",
            json={"role": "user", "content": "Cardiology question"},
            headers=gp_headers,
        )

        token = registered_specialist["access_token"]
        resp = client.get(f"/chats/{cardio['id']}/stream?token={token}")

        assert resp.status_code == 404
