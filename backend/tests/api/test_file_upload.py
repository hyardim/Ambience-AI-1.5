"""
Tests for POST /chats/{chat_id}/files — upload auth, validation, and persistence.
"""

import io
from unittest.mock import patch

_TXT_CONTENT = b"Patient summary: 34F with RRMS on interferon beta-1a."
_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f\n"
    b"0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
)


class TestFileUploadSuccess:
    def test_upload_txt_as_owner(self, client, gp_headers, created_chat, tmp_path):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("note.txt", io.BytesIO(_TXT_CONTENT), "text/plain")},
                headers=gp_headers,
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["filename"] == "note.txt"
        assert data["file_type"] == "text/plain"
        assert data["file_size"] == len(_TXT_CONTENT)
        assert "id" in data
        assert "created_at" in data

    def test_upload_pdf_as_owner(self, client, gp_headers, created_chat, tmp_path):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={
                    "file": ("guideline.pdf", io.BytesIO(_PDF_BYTES), "application/pdf")
                },
                headers=gp_headers,
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["filename"] == "guideline.pdf"
        assert data["file_type"] == "application/pdf"

    def test_upload_markdown_as_owner(self, client, gp_headers, created_chat, tmp_path):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("notes.md", io.BytesIO(b"# Note"), "text/markdown")},
                headers=gp_headers,
            )
        assert resp.status_code == 201
        assert resp.json()["filename"] == "notes.md"

    def test_upload_sanitises_nested_filename(
        self, client, gp_headers, created_chat, tmp_path
    ):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={
                    "file": (
                        "../folder/clinical note?.txt",
                        io.BytesIO(_TXT_CONTENT),
                        "text/plain",
                    )
                },
                headers=gp_headers,
            )
        assert resp.status_code == 201
        assert resp.json()["filename"] == "clinical_note_.txt"

    def test_upload_multiple_files_to_same_chat(
        self, client, gp_headers, created_chat, tmp_path
    ):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            for i in range(3):
                resp = client.post(
                    f"/chats/{created_chat['id']}/files",
                    files={
                        "file": (
                            f"doc{i}.txt",
                            io.BytesIO(f"content {i}".encode()),
                            "text/plain",
                        )
                    },
                    headers=gp_headers,
                )
                assert resp.status_code == 201

    def test_file_size_stored_correctly(
        self, client, gp_headers, created_chat, tmp_path
    ):
        content = b"Exact byte count matters."
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("note.txt", io.BytesIO(content), "text/plain")},
                headers=gp_headers,
            )
        assert resp.status_code == 201
        assert resp.json()["file_size"] == len(content)

    def test_uploaded_file_appears_in_chat_detail(
        self, client, gp_headers, created_chat, tmp_path
    ):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("summary.txt", io.BytesIO(_TXT_CONTENT), "text/plain")},
                headers=gp_headers,
            )
        detail = client.get(f"/chats/{created_chat['id']}", headers=gp_headers).json()
        assert len(detail["files"]) == 1
        assert detail["files"][0]["filename"] == "summary.txt"

    def test_multiple_files_all_appear_in_chat_detail(
        self, client, gp_headers, created_chat, tmp_path
    ):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            for name in ("a.txt", "b.txt", "c.txt"):
                client.post(
                    f"/chats/{created_chat['id']}/files",
                    files={"file": (name, io.BytesIO(b"content"), "text/plain")},
                    headers=gp_headers,
                )
        detail = client.get(f"/chats/{created_chat['id']}", headers=gp_headers).json()
        filenames = {f["filename"] for f in detail["files"]}
        assert filenames == {"a.txt", "b.txt", "c.txt"}


class TestFileUploadAuth:
    def test_upload_unauthenticated_fails(self, client, created_chat, tmp_path):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("note.txt", io.BytesIO(_TXT_CONTENT), "text/plain")},
            )
        assert resp.status_code == 401

    def test_upload_to_another_users_chat_fails(
        self, client, gp_headers, second_gp_headers, created_chat, tmp_path
    ):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("note.txt", io.BytesIO(_TXT_CONTENT), "text/plain")},
                headers=second_gp_headers,
            )
        assert resp.status_code == 403

    def test_upload_to_nonexistent_chat_fails(self, client, gp_headers, tmp_path):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                "/chats/99999/files",
                files={"file": ("note.txt", io.BytesIO(_TXT_CONTENT), "text/plain")},
                headers=gp_headers,
            )
        assert resp.status_code == 404

    def test_specialist_can_upload_to_assigned_chat(
        self,
        client,
        gp_headers,
        specialist_headers,
        registered_specialist,
        created_chat,
        tmp_path,
    ):
        # Send a message to auto-submit the chat, then assign the specialist
        client.post(
            f"/chats/{created_chat['id']}/message",
            json={"role": "user", "content": "Help needed."},
            headers=gp_headers,
        )
        client.post(
            f"/specialist/chats/{created_chat['id']}/assign",
            json={"specialist_id": registered_specialist["user"]["id"]},
            headers=specialist_headers,
        )
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={
                    "file": (
                        "specialist_note.txt",
                        io.BytesIO(b"Specialist note."),
                        "text/plain",
                    )
                },
                headers=specialist_headers,
            )
        assert resp.status_code == 201

    def test_unassigned_specialist_cannot_upload(
        self, client, specialist_headers, created_chat, tmp_path
    ):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("note.txt", io.BytesIO(_TXT_CONTENT), "text/plain")},
                headers=specialist_headers,
            )
        assert resp.status_code == 403


class TestFileUploadLimits:
    def test_oversized_file_returns_413(
        self, client, gp_headers, created_chat, tmp_path
    ):
        content = b"A" * (3 * 1024 * 1024 + 1)  # 3 MB + 1 byte
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("big.txt", io.BytesIO(content), "text/plain")},
                headers=gp_headers,
            )
        assert resp.status_code == 413
        assert "3 MB" in resp.json()["detail"]

    def test_file_at_exact_limit_is_accepted(
        self, client, gp_headers, created_chat, tmp_path
    ):
        content = b"A" * (3 * 1024 * 1024)  # exactly 3 MB
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={"file": ("exact.txt", io.BytesIO(content), "text/plain")},
                headers=gp_headers,
            )
        assert resp.status_code == 201

    def test_sixth_file_returns_422(self, client, gp_headers, created_chat, tmp_path):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            for i in range(5):
                client.post(
                    f"/chats/{created_chat['id']}/files",
                    files={
                        "file": (f"doc{i}.txt", io.BytesIO(b"content"), "text/plain")
                    },
                    headers=gp_headers,
                )
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={
                    "file": ("extra.txt", io.BytesIO(b"one too many"), "text/plain")
                },
                headers=gp_headers,
            )
        assert resp.status_code == 422
        assert "Maximum is 5" in resp.json()["detail"]

    def test_disallowed_extension_returns_415(
        self, client, gp_headers, created_chat, tmp_path
    ):
        with patch("src.services.chat_service.UPLOAD_DIR", tmp_path):
            resp = client.post(
                f"/chats/{created_chat['id']}/files",
                files={
                    "file": (
                        "malware.exe",
                        io.BytesIO(b"boom"),
                        "application/octet-stream",
                    )
                },
                headers=gp_headers,
            )
        assert resp.status_code == 415
        assert "not allowed" in resp.json()["detail"]
