"""Tests for the streaming generation helper and streamed /answer + /revise responses."""

import json

import pytest
import httpx

from src.generation.streaming import stream_generate


# ---------------------------------------------------------------------------
# Unit: stream_generate chunk parsing
# ---------------------------------------------------------------------------


class TestStreamGenerate:
    """Verify that stream_generate correctly parses Ollama NDJSON chunks."""

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self, monkeypatch):
        """stream_generate should raise RuntimeError on HTTP failure."""

        class FailStreamResponse:
            def raise_for_status(self):
                raise httpx.HTTPStatusError(
                    "500", request=httpx.Request("POST", "http://x"), response=httpx.Response(500)
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


# ---------------------------------------------------------------------------
# Unit: _streaming_generator NDJSON output (via the main module helper)
# ---------------------------------------------------------------------------

class TestStreamingGenerator:
    """Test the _streaming_generator that produces NDJSON for /answer and /revise."""

    @pytest.mark.asyncio
    async def test_produces_chunks_then_done(self, monkeypatch):
        """Should yield chunk lines followed by a done line."""
        from src.main import _streaming_generator, SearchResult

        tokens = ["Hello", " ", "world"]

        async def fake_stream_generate(prompt, max_tokens=None):
            for t in tokens:
                yield t

        monkeypatch.setattr("src.main.stream_generate", fake_stream_generate)

        citations_retrieved = [
            SearchResult(
                text="evidence",
                source="guideline.pdf",
                score=0.9,
            )
        ]

        lines = []
        async for line in _streaming_generator("prompt", 512, citations_retrieved):
            lines.append(json.loads(line.strip()))

        # Should have 3 chunk events + 1 done event
        assert len(lines) == 4
        assert lines[0] == {"type": "chunk", "delta": "Hello"}
        assert lines[1] == {"type": "chunk", "delta": " "}
        assert lines[2] == {"type": "chunk", "delta": "world"}
        assert lines[3]["type"] == "done"
        assert lines[3]["answer"] == "Hello world"
        assert "citations_retrieved" in lines[3]

    @pytest.mark.asyncio
    async def test_produces_error_on_failure(self, monkeypatch):
        """Should yield an error line if generation fails."""
        from src.main import _streaming_generator, SearchResult

        async def failing_stream(prompt, max_tokens=None):
            raise RuntimeError("model crashed")
            yield  # pragma: no cover

        monkeypatch.setattr("src.main.stream_generate", failing_stream)

        lines = []
        async for line in _streaming_generator("prompt", 512, []):
            lines.append(json.loads(line.strip()))

        assert len(lines) == 1
        assert lines[0]["type"] == "error"
        assert "model crashed" in lines[0]["error"]
