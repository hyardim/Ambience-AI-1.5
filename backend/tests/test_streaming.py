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
