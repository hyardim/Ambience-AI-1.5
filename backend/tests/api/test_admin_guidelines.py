"""
Tests for POST /admin/guidelines/upload

The endpoint proxies multipart PDF uploads to the RAG service via httpx.
All httpx calls are mocked so no real network or RAG service is needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

UPLOAD_URL = "/admin/guidelines/upload"

FAKE_REPORT = {
    "source_name": "NICE",
    "filename": "NG193.pdf",
    "files_scanned": 1,
    "files_succeeded": 1,
    "files_failed": 0,
    "total_chunks": 45,
    "embeddings_succeeded": 45,
    "embeddings_failed": 0,
    "db": {"inserted": 45, "updated": 0, "skipped": 0, "failed": 0},
}

PDF_BYTES = b"%PDF-1.4 fake pdf content"


def _mock_rag_success():
    """Return a mock httpx response with 200 and the fake report."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = FAKE_REPORT
    mock_resp.content = b"..."
    return mock_resp


def _mock_rag_error(status: int, detail: str):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status
    mock_resp.json.return_value = {"detail": detail}
    mock_resp.content = b"..."
    mock_resp.text = detail
    return mock_resp


# ---------------------------------------------------------------------------
# Auth / access control
# ---------------------------------------------------------------------------


class TestGuidelinesUploadAuth:
    def test_unauthenticated_returns_401(self, client):
        resp = client.post(
            UPLOAD_URL,
            files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
            data={"source_name": "NICE"},
        )
        assert resp.status_code == 401

    def test_gp_cannot_upload(self, client, gp_headers):
        resp = client.post(
            UPLOAD_URL,
            files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
            data={"source_name": "NICE"},
            headers=gp_headers,
        )
        assert resp.status_code == 403

    def test_specialist_cannot_upload(self, client, specialist_headers):
        resp = client.post(
            UPLOAD_URL,
            files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
            data={"source_name": "NICE"},
            headers=specialist_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestGuidelinesUploadValidation:
    def test_non_pdf_rejected(self, client, admin_headers):
        resp = client.post(
            UPLOAD_URL,
            files={"file": ("notes.txt", b"some text", "text/plain")},
            data={"source_name": "NICE"},
            headers=admin_headers,
        )
        assert resp.status_code == 422
        assert "pdf" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestGuidelinesUploadSuccess:
    def test_successful_upload_returns_report(self, client, admin_headers):
        mock_resp = _mock_rag_success()

        with patch("src.api.admin.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_async_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_async_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = client.post(
                UPLOAD_URL,
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
                headers=admin_headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["source_name"] == "NICE"
        assert body["filename"] == "NG193.pdf"
        assert body["total_chunks"] == 45
        assert body["embeddings_succeeded"] == 45
        assert body["db"]["inserted"] == 45
        assert body["db"]["failed"] == 0

    def test_rag_called_with_correct_args(self, client, admin_headers):
        mock_resp = _mock_rag_success()

        with patch("src.api.admin.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_async_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_async_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            client.post(
                UPLOAD_URL,
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "BSR"},
                headers=admin_headers,
            )

            call_kwargs = mock_async_client.post.call_args
            assert "source_name" in str(call_kwargs)
            assert "BSR" in str(call_kwargs)


# ---------------------------------------------------------------------------
# RAG service error propagation
# ---------------------------------------------------------------------------


class TestGuidelinesUploadRagErrors:
    def test_rag_unavailable_returns_502(self, client, admin_headers):
        with patch("src.api.admin.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_async_client.post = AsyncMock(
                side_effect=httpx.ConnectError("refused")
            )
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_async_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = client.post(
                UPLOAD_URL,
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
                headers=admin_headers,
            )

        assert resp.status_code == 502

    def test_rag_timeout_returns_504(self, client, admin_headers):
        with patch("src.api.admin.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_async_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_async_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = client.post(
                UPLOAD_URL,
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
                headers=admin_headers,
            )

        assert resp.status_code == 504

    def test_rag_422_propagated(self, client, admin_headers):
        mock_resp = _mock_rag_error(422, "Unknown source 'FAKE'.")

        with patch("src.api.admin.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_async_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_async_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = client.post(
                UPLOAD_URL,
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "FAKE"},
                headers=admin_headers,
            )

        assert resp.status_code == 422
        assert "FAKE" in resp.json()["detail"]

    def test_rag_500_propagated(self, client, admin_headers):
        mock_resp = _mock_rag_error(500, "Pipeline failed at stage embed: OOM")

        with patch("src.api.admin.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_async_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_async_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = client.post(
                UPLOAD_URL,
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
                headers=admin_headers,
            )

        assert resp.status_code == 500
