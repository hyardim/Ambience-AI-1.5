import sys
import types
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

from src.services import chat_service, chat_uploads, rag_context, specialist_review


def test_looks_like_text_handles_empty_and_binary_samples():
    assert chat_uploads._looks_like_text(b"") is True
    assert chat_uploads._looks_like_text(b"Clinical notes") is True
    assert chat_uploads._looks_like_text(b"\x00\x01\x02binary") is False


def test_validate_upload_content_accepts_known_binary_signatures():
    chat_uploads.validate_upload_content("summary.docx", None, b"PK\x03\x04rest")
    chat_uploads.validate_upload_content(
        "summary.doc", None, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest"
    )
    chat_uploads.validate_upload_content("summary.rtf", None, b"{\\rtf1\\ansi text")


def test_validate_upload_content_rejects_invalid_doc_signatures():
    with pytest.raises(HTTPException, match="valid DOCX"):
        chat_uploads.validate_upload_content("bad.docx", None, b"NOTZIP")

    with pytest.raises(HTTPException, match="valid DOC"):
        chat_uploads.validate_upload_content("bad.doc", None, b"NOTOLE")

    with pytest.raises(HTTPException, match="valid RTF"):
        chat_uploads.validate_upload_content("bad.rtf", None, b"{not-rtf")


def test_validate_upload_content_rejects_binary_mime_for_text_extension():
    with pytest.raises(HTTPException, match="Binary MIME type"):
        chat_uploads.validate_upload_content(
            "notes.txt", "application/octet-stream", b"normal text"
        )


def test_validate_upload_content_rejects_non_text_payload_for_text_extension():
    with pytest.raises(HTTPException, match="does not match"):
        chat_uploads.validate_upload_content(
            "notes.txt", "text/plain", b"\x00\x01\x02\x03"
        )


def test_file_context_wrapper_functions_remain_backwards_compatible():
    fake_chat = SimpleNamespace(files=[])

    assert rag_context.build_file_context(fake_chat) is None
    assert chat_service._build_file_context(fake_chat) is None
    assert chat_service._build_file_context_result(fake_chat).file_context is None
    assert specialist_review._build_file_context(fake_chat) is None
    assert specialist_review._build_file_context_result(fake_chat).file_context is None


def test_build_conversation_history_breaks_when_budget_exceeded_after_tail_kept():
    messages = [
        SimpleNamespace(content="Older context", sender="user", is_error=False),
        SimpleNamespace(
            content="Most recent specialist advice", sender="specialist", is_error=False
        ),
    ]

    history = rag_context.build_conversation_history_from_messages(
        messages,
        token_budget=3,
    )

    assert history == "Specialist: Most recent specialist advice"


@pytest.mark.asyncio
async def test_upload_chat_file_deduplicates_existing_filename(
    db_session, monkeypatch, tmp_path
):
    from src.db.models import Chat, FileAttachment, User, UserRole

    owner = User(
        email="upload-owner@example.com",
        hashed_password="hash",
        full_name="Upload Owner",
        role=UserRole.GP,
        is_active=True,
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    chat = Chat(user_id=owner.id, title="Upload Chat")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    upload_dir = tmp_path / str(chat.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    existing_path = upload_dir / "report.txt"
    existing_path.write_text("existing")

    monkeypatch.setattr(chat_uploads, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        chat_uploads.audit_repository, "log", lambda *args, **kwargs: None
    )

    async def _noop_delete_pattern(*args, **kwargs):
        return None

    async def _noop_invalidate(*args, **kwargs):
        return None

    monkeypatch.setattr(chat_uploads.cache, "delete_pattern", _noop_delete_pattern)
    monkeypatch.setattr(chat_uploads, "invalidate_chat_related_async", _noop_invalidate)

    upload = UploadFile(
        filename="report.txt",
        file=BytesIO(b"fresh content"),
        headers={"content-type": "text/plain"},
    )

    attachment = await chat_uploads.upload_chat_file(
        db_session,
        owner,
        chat.id,
        upload,
    )

    assert attachment.filename == "report_1.txt"
    assert (upload_dir / "report_1.txt").read_text() == "fresh content"
    assert db_session.query(FileAttachment).count() == 1


def test_extract_text_returns_pdf_text_when_reader_succeeds(monkeypatch, tmp_path):
    class FakeReader:
        def __init__(self, _path):
            self.pages = [SimpleNamespace(extract_text=lambda: "A" * 60)]

    monkeypatch.setitem(
        sys.modules, "pypdf", types.SimpleNamespace(PdfReader=FakeReader)
    )

    result = rag_context.extract_text(str(tmp_path / "doc.pdf"), "application/pdf")

    assert result == "A" * 60


def test_build_file_context_result_prefers_sentence_boundary_when_truncating(
    monkeypatch,
):
    monkeypatch.setattr(rag_context, "FILE_CONTEXT_CHAR_LIMIT", 45)
    chat = SimpleNamespace(
        files=[
            SimpleNamespace(
                filename="note.txt",
                file_path="/tmp/note.txt",
                file_type="text/plain",
            )
        ]
    )
    text = (
        "Sentence one is quite long. Sentence two should be removed entirely afterward."
    )

    result = rag_context.build_file_context_result(
        chat, extract_text_fn=lambda *_args: text
    )

    assert result.was_truncated is True
    assert "Sentence one is quite long." in (result.file_context or "")
    assert "Sentence two should be removed" not in (result.file_context or "")


def test_build_file_context_result_falls_back_to_word_boundary_when_truncating(
    monkeypatch,
):
    monkeypatch.setattr(rag_context, "FILE_CONTEXT_CHAR_LIMIT", 55)
    chat = SimpleNamespace(
        files=[
            SimpleNamespace(
                filename="note.txt",
                file_path="/tmp/note.txt",
                file_type="text/plain",
            )
        ]
    )
    text = (
        "Wordboundary truncation should stop before clipping the finalwordwithoutperiod"
    )

    result = rag_context.build_file_context_result(
        chat, extract_text_fn=lambda *_args: text
    )

    assert result.was_truncated is True
    assert "finalwordwithoutperiod" not in (result.file_context or "")
