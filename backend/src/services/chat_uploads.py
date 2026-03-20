from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import cast

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.models import FileAttachment, User
from src.repositories import audit_repository, chat_repository
from src.services.cache_invalidation import invalidate_chat_related_async
from src.utils.cache import cache, cache_keys

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
MAX_FILE_SIZE_BYTES = settings.MAX_FILE_SIZE_BYTES
MAX_FILES_PER_CHAT = settings.MAX_FILES_PER_CHAT
ALLOWED_UPLOAD_EXTENSIONS = {ext.lower() for ext in settings.ALLOWED_UPLOAD_EXTENSIONS}
UPLOAD_CHUNK_BYTES = 64 * 1024
SIGNATURE_SAMPLE_BYTES = 4096

_SAFE_FILENAME_RE = re.compile(r"[^\w\-.]", re.ASCII)
_BINARY_CONTROL_BYTES_RE = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitise_filename(raw: str) -> str:
    """Strip path components and unsafe characters from a user-supplied filename."""
    name = PurePosixPath(raw).name
    if not name:
        name = "upload"
    name = _SAFE_FILENAME_RE.sub("_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:255] if name else "upload"


def validate_upload_extension(filename: str) -> None:
    """Raise 415 if the file extension is not in the allow-list."""
    ext = PurePosixPath(filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"File type '{ext or '(none)'}' is not allowed. "
                f"Accepted types: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
            ),
        )


def _looks_like_text(sample: bytes) -> bool:
    if not sample:
        return True
    if b"\x00" in sample:
        return False
    control_bytes = _BINARY_CONTROL_BYTES_RE.findall(sample)
    return (len(control_bytes) / len(sample)) <= 0.02


def validate_upload_content(
    filename: str,
    content_type: str | None,
    sample: bytes,
) -> None:
    """Validate file content using signatures/text heuristics, not extension alone."""
    ext = PurePosixPath(filename).suffix.lower()
    lowered = sample[:SIGNATURE_SAMPLE_BYTES]

    if ext == ".pdf" and not lowered.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=415, detail="Uploaded content is not a valid PDF"
        )
    if ext == ".docx" and not lowered.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        raise HTTPException(
            status_code=415, detail="Uploaded content is not a valid DOCX"
        )
    if ext == ".doc" and not lowered.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise HTTPException(
            status_code=415, detail="Uploaded content is not a valid DOC"
        )
    if ext == ".rtf" and not lowered.lstrip().startswith(b"{\\rtf"):
        raise HTTPException(
            status_code=415, detail="Uploaded content is not a valid RTF"
        )

    text_extensions = {".txt", ".md", ".csv", ".json", ".xml"}
    if ext in text_extensions and not _looks_like_text(lowered):
        raise HTTPException(
            status_code=415,
            detail="Uploaded content does not match the declared text file type",
        )

    if content_type:
        generic_binary_mime = "application/octet-stream"
        if ext in text_extensions and content_type == generic_binary_mime:
            raise HTTPException(
                status_code=415,
                detail="Binary MIME type is not allowed for plain-text uploads",
            )


async def _stream_upload_to_path(
    file: UploadFile, dest_path: Path
) -> tuple[int, bytes]:
    """Write upload to disk in chunks while enforcing size limits."""
    total_size = 0
    signature = bytearray()

    with dest_path.open("wb") as out:
        while True:
            chunk = await file.read(UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE_BYTES:
                limit_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"File exceeds the {limit_mb} MB limit "
                        f"({total_size // 1024} KB uploaded)."
                    ),
                )
            if len(signature) < SIGNATURE_SAMPLE_BYTES:
                remaining = SIGNATURE_SAMPLE_BYTES - len(signature)
                signature.extend(chunk[:remaining])
            out.write(chunk)

    return total_size, bytes(signature)


async def upload_chat_file(
    db: Session,
    user: User,
    chat_id: int,
    file: UploadFile,
) -> FileAttachment:
    from src.core.chat_policy import can_upload_to_chat

    chat = chat_repository.get(db, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    uploader_id = cast(int, user.id)
    owner_id = cast(int, chat.user_id)
    specialist_id = cast(int | None, chat.specialist_id)
    specialty = cast(str | None, chat.specialty)

    if not can_upload_to_chat(user, chat):
        raise HTTPException(
            status_code=403, detail="Not authorised to upload to this chat"
        )

    safe_name = sanitise_filename(file.filename or "upload")
    validate_upload_extension(safe_name)

    existing_count = (
        db.query(FileAttachment).filter(FileAttachment.chat_id == chat_id).count()
    )
    if existing_count >= MAX_FILES_PER_CHAT:
        raise HTTPException(
            status_code=422,
            detail=f"Chat already has {existing_count} files. Maximum is {MAX_FILES_PER_CHAT}.",
        )

    dest_dir = UPLOAD_DIR / str(chat_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_name

    try:
        file_size, signature = await _stream_upload_to_path(file, dest_path)
        validate_upload_content(safe_name, file.content_type, signature)
    except Exception:
        if dest_path.exists():
            dest_path.unlink()
        raise

    attachment = FileAttachment(
        filename=safe_name,
        file_path=str(dest_path),
        file_type=file.content_type,
        file_size=file_size,
        chat_id=chat_id,
        uploader_id=uploader_id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    audit_repository.log(
        db,
        user_id=uploader_id,
        action="UPLOAD_FILE",
        details=f"Uploaded {file.filename} to chat {chat_id}",
        invalidate_admin_cache=False,
    )
    await cache.delete_pattern(
        cache_keys.chat_detail_pattern(chat_id),
        user_id=uploader_id,
        resource="chat_detail",
    )
    await cache.delete_pattern(
        cache_keys.chat_list_pattern(owner_id),
        user_id=owner_id,
        resource="chat_list",
    )
    await cache.delete_pattern(
        cache_keys.admin_audit_logs_pattern(), resource="admin_audit_logs"
    )
    await invalidate_chat_related_async(
        chat_id=chat_id,
        user_id=owner_id,
        specialty=specialty,
        specialist_id=specialist_id,
    )

    return attachment
