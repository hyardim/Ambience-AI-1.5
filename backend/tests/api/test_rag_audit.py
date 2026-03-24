"""
Tests for sub-issue 2 — RAG audit logging.

RAG_ANSWER is logged when the RAG service returns a successful response.
RAG_ERROR  is logged when the RAG service is unavailable (the normal test
           environment state, since no real Ollama server is running).

The rag_grounded_responses stat only counts messages whose citations column
is NOT NULL (i.e. real sources were retrieved).
"""

from unittest.mock import AsyncMock, MagicMock, patch


def _send_message(client, chat_id, headers, content="Patient has wrist pain."):
    return client.post(
        f"/chats/{chat_id}/message",
        json={"role": "user", "content": content},
        headers=headers,
    )


def _create_chat(client, headers, specialty="neurology"):
    resp = client.post(
        "/chats/", json={"title": "RAG test", "specialty": specialty}, headers=headers
    )
    assert resp.status_code == 200
    return resp.json()


def _mock_async_client(response):
    """Return a mock httpx.AsyncClient that works as an async context manager."""
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=response)
    return mock_client


# ---------------------------------------------------------------------------
# RAG_ERROR logged when service is unavailable (default test environment)
# ---------------------------------------------------------------------------


class TestRAGErrorLogging:
    def test_rag_error_logged_on_service_failure(
        self, client, admin_headers, gp_headers
    ):
        chat = _create_chat(client, gp_headers)
        _send_message(client, chat["id"], gp_headers)

        logs = client.get("/admin/logs", headers=admin_headers).json()
        rag_logs = [
            log_entry
            for log_entry in logs
            if log_entry["action"] in ("RAG_ANSWER", "RAG_ERROR")
        ]
        assert len(rag_logs) >= 1

    def test_rag_error_category_is_rag(self, client, admin_headers, gp_headers):
        chat = _create_chat(client, gp_headers)
        _send_message(client, chat["id"], gp_headers)

        logs = client.get("/admin/logs", headers=admin_headers).json()
        rag_logs = [
            log_entry
            for log_entry in logs
            if log_entry["action"] in ("RAG_ANSWER", "RAG_ERROR")
        ]
        for log in rag_logs:
            assert log["category"] == "RAG"

    def test_rag_error_does_not_increment_grounded_stat(
        self, client, admin_headers, gp_headers
    ):
        chat = _create_chat(client, gp_headers)
        _send_message(client, chat["id"], gp_headers)

        data = client.get("/admin/stats", headers=admin_headers).json()
        assert data["rag_grounded_responses"] == 0

    def test_total_ai_responses_increments_even_on_rag_error(
        self, client, admin_headers, gp_headers
    ):
        chat = _create_chat(client, gp_headers)
        _send_message(client, chat["id"], gp_headers)

        data = client.get("/admin/stats", headers=admin_headers).json()
        assert data["total_ai_responses"] >= 1


# ---------------------------------------------------------------------------
# RAG_ANSWER logged when service returns valid response (mocked)
# ---------------------------------------------------------------------------


class TestRAGAnswerLogging:
    def _mock_rag_response(self, citations=None):
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = {
            "answer": "Based on NICE guidelines, the recommended treatment is...",
            "citations_used": (
                citations
                if citations is not None
                else [{"source": "NICE CG101", "chunk": "..."}]
            ),
        }
        return mock

    def test_rag_answer_logged_on_success(self, client, admin_headers, gp_headers):
        mock_response = self._mock_rag_response()
        with patch(
            "src.services.chat_service.httpx.post",
            return_value=mock_response,
        ), patch(
            "src.services.chat_service.httpx.AsyncClient",
            return_value=_mock_async_client(mock_response),
        ):
            chat = _create_chat(client, gp_headers)
            _send_message(client, chat["id"], gp_headers)

        logs = client.get("/admin/logs", headers=admin_headers).json()
        rag_answer_logs = [
            log_entry for log_entry in logs if log_entry["action"] == "RAG_ANSWER"
        ]
        assert len(rag_answer_logs) >= 1

    def test_rag_answer_category_is_rag(self, client, admin_headers, gp_headers):
        mock_response = self._mock_rag_response()
        with patch(
            "src.services.chat_service.httpx.post",
            return_value=mock_response,
        ), patch(
            "src.services.chat_service.httpx.AsyncClient",
            return_value=_mock_async_client(mock_response),
        ):
            chat = _create_chat(client, gp_headers)
            _send_message(client, chat["id"], gp_headers)

        logs = client.get("/admin/logs", headers=admin_headers).json()
        for log in [
            log_entry for log_entry in logs if log_entry["action"] == "RAG_ANSWER"
        ]:
            assert log["category"] == "RAG"

    def test_rag_grounded_stat_increments_on_answer_with_citations(
        self, client, admin_headers, gp_headers
    ):
        mock_response = self._mock_rag_response()
        with patch(
            "src.services.chat_service.httpx.post",
            return_value=mock_response,
        ), patch(
            "src.services.chat_service.httpx.AsyncClient",
            return_value=_mock_async_client(mock_response),
        ):
            chat = _create_chat(client, gp_headers)
            _send_message(client, chat["id"], gp_headers)

        data = client.get("/admin/stats", headers=admin_headers).json()
        assert data["rag_grounded_responses"] >= 1
        assert data["total_ai_responses"] >= 1

    def test_rag_grounded_stat_zero_when_no_citations_returned(
        self, client, admin_headers, gp_headers
    ):
        """RAG succeeds but returns empty citations → not counted as grounded."""
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = {"answer": "I don't know.", "citations_used": []}

        with patch(
            "src.services.chat_service.httpx.AsyncClient",
            return_value=_mock_async_client(mock),
        ):
            chat = _create_chat(client, gp_headers)
            _send_message(client, chat["id"], gp_headers)

        data = client.get("/admin/stats", headers=admin_headers).json()
        assert data["rag_grounded_responses"] == 0

    def test_rag_log_details_contain_chunk_count(
        self, client, admin_headers, gp_headers
    ):
        citations = [{"source": "NICE", "chunk": "a"}, {"source": "BMJ", "chunk": "b"}]
        mock_response = self._mock_rag_response(citations)
        with patch(
            "src.services.chat_service.httpx.post",
            return_value=mock_response,
        ), patch(
            "src.services.chat_service.httpx.AsyncClient",
            return_value=_mock_async_client(mock_response),
        ):
            chat = _create_chat(client, gp_headers)
            _send_message(client, chat["id"], gp_headers)

        logs = client.get("/admin/logs", headers=admin_headers).json()
        rag_log = next(
            (log_entry for log_entry in logs if log_entry["action"] == "RAG_ANSWER"),
            None,
        )
        assert rag_log is not None
        assert "chunks_used=2" in rag_log["details"]
