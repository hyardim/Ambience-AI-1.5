"""
Tests for file_context construction and forwarding to the RAG service:
covers single file, multiple files, truncation cap, and no-file baseline.
"""

import io
from unittest.mock import MagicMock, patch


def _fake_rag_factory(captured: dict):
    """Return a fake httpx.post that records the RAG payload and returns a stub response."""
    def _fake(url, json, timeout):
        captured.update(json)
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {
            "answer": "Test answer",
            "citations": [],
            "citations_used": [],
            "citations_retrieved": [],
        }
        return m
    return _fake


class TestFileContextRAGPayload:

    def test_file_context_included_when_file_uploaded(
        self, client, gp_headers, created_chat, tmp_path
    ):
        content = b"NICE NG220: Offer natalizumab for rapidly evolving severe RRMS."
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("guideline.txt", io.BytesIO(content), "text/plain")},
                headers=gp_headers,
            )

        captured = {}
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path), \
             patch("src.services.chat_service.httpx.post", side_effect=_fake_rag_factory(captured)):
            client.post(
                f"/chats/{created_chat['id']}/message",
                json={"role": "user", "content": "What DMT is recommended?"},
                headers=gp_headers,
            )

        assert "file_context" in captured
        assert "natalizumab" in captured["file_context"]

    def test_file_context_absent_when_no_files_uploaded(
        self, client, gp_headers, created_chat
    ):
        captured = {}
        with patch("src.services.chat_service.httpx.post", side_effect=_fake_rag_factory(captured)):
            client.post(
                f"/chats/{created_chat['id']}/message",
                json={"role": "user", "content": "What DMT is recommended?"},
                headers=gp_headers,
            )

        assert "file_context" not in captured

    def test_multiple_files_concatenated_in_file_context(
        self, client, gp_headers, created_chat, tmp_path
    ):
        files = [
            ("doc1.txt", b"First document: natalizumab criteria."),
            ("doc2.txt", b"Second document: ocrelizumab criteria."),
        ]
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            for name, content in files:
                client.post(
                    f"/chats/{created_chat['id']}/files",
                    files={"file": (name, io.BytesIO(content), "text/plain")},
                    headers=gp_headers,
                )

        captured = {}
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path), \
             patch("src.services.chat_service.httpx.post", side_effect=_fake_rag_factory(captured)):
            client.post(
                f"/chats/{created_chat['id']}/message",
                json={"role": "user", "content": "Summarise."},
                headers=gp_headers,
            )

        fc = captured.get("file_context", "")
        assert "natalizumab" in fc
        assert "ocrelizumab" in fc

    def test_file_context_truncated_at_8000_chars(
        self, client, gp_headers, created_chat, tmp_path
    ):
        long_content = b"A" * 20_000
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("big.txt", io.BytesIO(long_content), "text/plain")},
                headers=gp_headers,
            )

        captured = {}
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path), \
             patch("src.services.chat_service.httpx.post", side_effect=_fake_rag_factory(captured)):
            client.post(
                f"/chats/{created_chat['id']}/message",
                json={"role": "user", "content": "Summarise."},
                headers=gp_headers,
            )

        fc = captured.get("file_context", "")
        assert len(fc) <= 8_100  # cap + truncation message overhead
        assert "truncated" in fc.lower()

    def test_file_context_not_truncated_when_under_limit(
        self, client, gp_headers, created_chat, tmp_path
    ):
        content = b"Short clinical note." * 10  # well under 8,000 chars
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("note.txt", io.BytesIO(content), "text/plain")},
                headers=gp_headers,
            )

        captured = {}
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path), \
             patch("src.services.chat_service.httpx.post", side_effect=_fake_rag_factory(captured)):
            client.post(
                f"/chats/{created_chat['id']}/message",
                json={"role": "user", "content": "Summarise."},
                headers=gp_headers,
            )

        fc = captured.get("file_context", "")
        assert "truncated" not in fc.lower()
        assert "Short clinical note" in fc

    def test_filename_label_included_in_file_context(
        self, client, gp_headers, created_chat, tmp_path
    ):
        """Each file's content should be prefixed with its filename."""
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("discharge_summary.txt", io.BytesIO(b"Patient discharged well."), "text/plain")},
                headers=gp_headers,
            )

        captured = {}
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path), \
             patch("src.services.chat_service.httpx.post", side_effect=_fake_rag_factory(captured)):
            client.post(
                f"/chats/{created_chat['id']}/message",
                json={"role": "user", "content": "What happened?"},
                headers=gp_headers,
            )

        fc = captured.get("file_context", "")
        assert "discharge_summary.txt" in fc
