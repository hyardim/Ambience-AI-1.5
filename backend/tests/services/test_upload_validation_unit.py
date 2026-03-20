from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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
