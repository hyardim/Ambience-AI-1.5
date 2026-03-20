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

_SAFE_FILENAME_RE = re.compile(r"[^\w\-.]", re.ASCII)


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

    dest_dir = UPLOAD_DIR / str(chat_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_name

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE_BYTES:
        limit_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {limit_mb} MB limit ({len(contents) // 1024} KB uploaded).",
        )

    existing_count = (
        db.query(FileAttachment).filter(FileAttachment.chat_id == chat_id).count()
    )
    if existing_count >= MAX_FILES_PER_CHAT:
        raise HTTPException(
            status_code=422,
            detail=f"Chat already has {existing_count} files. Maximum is {MAX_FILES_PER_CHAT}.",
        )

    dest_path.write_bytes(contents)

    attachment = FileAttachment(
        filename=safe_name,
        file_path=str(dest_path),
        file_type=file.content_type,
        file_size=len(contents),
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
