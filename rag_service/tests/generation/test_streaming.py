"""Tests for the streaming helper and streamed /answer + /revise responses."""

import json

import httpx
import pytest

from src.generation.streaming import stream_generate


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Unit: stream_generate chunk parsing
# ---------------------------------------------------------------------------


class TestStreamGenerate:
    """Verify that stream_generate correctly parses Ollama NDJSON chunks."""

    @pytest.mark.anyio
    async def test_yields_tokens_from_ollama_stream(self, monkeypatch):
        """stream_generate should yield individual token strings."""
        chunks = [
            json.dumps({"response": "Hello", "done": False}),
            json.dumps({"response": " world", "done": False}),
            json.dumps({"response": "", "done": True}),
        ]

        class FakeStreamResponse:
            async def aiter_lines(self):
                for c in chunks:
                    yield c

            def raise_for_status(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeClient:
            def stream(self, method, url, json=None):
                return FakeStreamResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())

        tokens = []
        async for token in stream_generate("test prompt"):
            tokens.append(token)

        assert tokens == ["Hello", " world"]

    @pytest.mark.anyio
    async def test_accumulates_full_answer(self, monkeypatch):
        """Caller can accumulate tokens into a full answer."""
        chunks = [
            json.dumps({"response": "A", "done": False}),
            json.dumps({"response": "B", "done": False}),
            json.dumps({"response": "C", "done": True}),
        ]

        class FakeStreamResponse:
            async def aiter_lines(self):
                for c in chunks:
                    yield c

            def raise_for_status(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeClient:
            def stream(self, method, url, json=None):
                return FakeStreamResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())

        accumulated = ""
        async for token in stream_generate("test"):
            accumulated += token

        assert accumulated == "ABC"

    @pytest.mark.anyio
    async def test_skips_blank_lines(self, monkeypatch):
        """Blank lines in the stream should be silently skipped."""
        chunks = [
            "",
            json.dumps({"response": "ok", "done": False}),
            "  ",
            json.dumps({"response": "", "done": True}),
        ]

        class FakeStreamResponse:
            async def aiter_lines(self):
                for c in chunks:
                    yield c

            def raise_for_status(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeClient:
            def stream(self, method, url, json=None):
                return FakeStreamResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())

        tokens = []
        async for token in stream_generate("q"):
            tokens.append(token)

        assert tokens == ["ok"]

    @pytest.mark.anyio
    async def test_raises_on_http_error(self, monkeypatch):
        """stream_generate should raise RuntimeError on HTTP failure."""

        class FailStreamResponse:
            def raise_for_status(self):
                raise httpx.HTTPStatusError(
                    "500",
                    request=httpx.Request("POST", "http://x"),
                    response=httpx.Response(500),
                )

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FailClient:
            def stream(self, method, url, json=None):
                return FailStreamResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FailClient())

        with pytest.raises(RuntimeError, match="Ollama streaming request failed"):
            async for _ in stream_generate("q"):
                pass

    @pytest.mark.anyio
    async def test_skips_invalid_json_lines(self, monkeypatch):
        chunks = [
            "{bad json",
            json.dumps({"response": "ok", "done": False}),
            json.dumps({"response": "", "done": True}),
        ]

        class FakeStreamResponse:
            async def aiter_lines(self):
                for chunk in chunks:
                    yield chunk

            def raise_for_status(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeClient:
            def stream(self, method, url, json=None):
                return FakeStreamResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())

        tokens = []
        async for token in stream_generate("q"):
            tokens.append(token)

        assert tokens == ["ok"]

    @pytest.mark.anyio
    async def test_uses_configured_timeout(self, monkeypatch):
        captured_timeout = None
        captured_payload = None

        class FakeStreamResponse:
            async def aiter_lines(self):
                yield json.dumps({"response": "", "done": True})

            def raise_for_status(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeClient:
            def __init__(self, *, timeout):
                nonlocal captured_timeout
                captured_timeout = timeout

            def stream(self, method, url, json=None):
                nonlocal captured_payload
                captured_payload = json
                return FakeStreamResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
        monkeypatch.setattr(
            "src.generation.streaming.local_llm_config",
            type(
                "Cfg",
                (),
                {
                    "timeout_seconds": 17.5,
                    "model": "m",
                    "base_url": "http://x",
                    "max_tokens": 10,
                    "temperature": 0.0,
                },
            )(),
        )

        async for _ in stream_generate("q"):
            pass

        assert captured_timeout == 17.5
        assert captured_payload is not None
        assert captured_payload.get("options", {}).get("temperature") == 0.0
