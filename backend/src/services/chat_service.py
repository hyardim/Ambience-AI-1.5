import os
from pathlib import Path
from typing import Optional

import httpx
from fastapi import BackgroundTasks, HTTPException, UploadFile
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.models import ChatStatus, FileAttachment, User
from src.db.session import SessionLocal
from src.repositories import audit_repository, chat_repository, message_repository
from src.schemas.chat import (
    ChatCreate,
    ChatResponse,
    ChatUpdate,
    ChatWithMessages,
    FileAttachmentResponse,
)
from src.services._mappers import chat_to_response, msg_to_response
from src.utils.cache import cache, cache_keys


RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag_service:8001")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
MAX_FILE_SIZE_BYTES = 3 * 1024 * 1024  # 3 MB per file
MAX_FILES_PER_CHAT = 5
RAG_REQUEST_TIMEOUT_SECONDS = float(
    os.getenv("RAG_REQUEST_TIMEOUT_SECONDS", "120"))


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_chat(db: Session, user: User, data: ChatCreate) -> ChatResponse:
    patient_context = {
        k: v
        for k, v in {
            "age": data.patient_age,
            "gender": data.patient_gender,
            "notes": data.patient_notes,
        }.items()
        if v is not None
    } or None

    chat = chat_repository.create(
        db,
        user_id=user.id,
        title=data.title,
        specialty=data.specialty,
        severity=data.severity,
        patient_context=patient_context,
    )
    audit_repository.log(
        db, user_id=user.id, action="CREATE_CHAT", details=f"Created chat: {data.title}"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(user.id), user_id=user.id, resource="chat_list"
    )
    return chat_to_response(chat)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def list_chats(
    db: Session,
    user: User,
    *,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    specialty: Optional[str] = None,
) -> list[ChatResponse]:
    if status:
        try:
            ChatStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid status: {status}")

    page = skip // limit if limit else 0
    cache_key = cache_keys.chat_list(
        user.id, page, limit, status=status, specialty=specialty)
    cached = cache.get_sync(cache_key, user_id=user.id, resource="chat_list")
    if cached is not None:
        return [ChatResponse(**item) for item in cached]

    chats = chat_repository.list_for_user(
        db, user.id, skip=skip, limit=limit, status=status, specialty=specialty
    )
    response = [chat_to_response(c) for c in chats]
    cache.set_sync(
        cache_key,
        [item.model_dump() for item in response],
        ttl=settings.CACHE_CHAT_LIST_TTL,
        user_id=user.id,
        resource="chat_list",
    )
    return response


# ---------------------------------------------------------------------------
# Get (with messages)
# ---------------------------------------------------------------------------


def get_chat(db: Session, user: User, chat_id: int) -> ChatWithMessages:
    cache_key = cache_keys.chat_detail(user.id, chat_id)
    cached = cache.get_sync(cache_key, user_id=user.id, resource="chat_detail")
    if cached is not None:
        return ChatWithMessages(**cached)

    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    audit_repository.log(
        db, user_id=user.id, action="VIEW_CHAT", details=f"Viewed chat {chat_id}"
    )
    messages = message_repository.list_for_chat(db, chat.id)
    response = ChatWithMessages(**chat_to_response(chat).model_dump())
    response.messages = [msg_to_response(m) for m in messages]
    response.files = [
        FileAttachmentResponse(
            id=f.id,
            filename=f.filename,
            file_type=f.file_type,
            file_size=f.file_size,
            created_at=f.created_at.isoformat() if f.created_at else "",
        )
        for f in (chat.files or [])
    ]
    cache.set_sync(
        cache_key,
        response.model_dump(),
        ttl=settings.CACHE_CHAT_DETAIL_TTL,
        user_id=user.id,
        resource="chat_detail",
    )
    return response


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def update_chat(
    db: Session, user: User, chat_id: int, payload: ChatUpdate
) -> ChatResponse:
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Block metadata edits after specialist assignment
    if chat.status not in (ChatStatus.OPEN, ChatStatus.SUBMITTED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit chat details after specialist assignment (current: {chat.status.value})",
        )

    fields: dict = {}
    if payload.title is not None:
        fields["title"] = payload.title
    if payload.specialty is not None:
        fields["specialty"] = payload.specialty
    if payload.severity is not None:
        fields["severity"] = payload.severity
    if payload.status is not None:
        try:
            fields["status"] = ChatStatus(payload.status)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid status: {payload.status}"
            )

    chat = chat_repository.update(db, chat, **fields)
    audit_repository.log(
        db, user_id=user.id, action="UPDATE_CHAT", details=f"Updated chat {chat_id}"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(user.id), user_id=user.id, resource="chat_list"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat_id), user_id=user.id, resource="chat_detail"
    )
    return chat_to_response(chat)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def delete_chat(db: Session, user: User, chat_id: int) -> None:
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat_repository.delete(db, chat)
    audit_repository.log(
        db, user_id=user.id, action="DELETE_CHAT", details=f"Deleted chat {chat_id}"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(user.id), user_id=user.id, resource="chat_list"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat_id), user_id=user.id, resource="chat_detail"
    )


# ---------------------------------------------------------------------------
# File uploads
# ---------------------------------------------------------------------------


def _extract_text(file_path: str, file_type: Optional[str]) -> str:
    """Extract plain text from an uploaded file (PDF or plain text)."""
    try:
        if file_type and "pdf" in file_type.lower():
            from pypdf import PdfReader  # lazy import — only used when PDF is uploaded
            reader = PdfReader(file_path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            return Path(file_path).read_text(errors="replace")
    except Exception:
        return ""


async def upload_file(
    db: Session,
    user: User,
    chat_id: int,
    file: UploadFile,
) -> FileAttachmentResponse:
    chat = chat_repository.get(db, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Only the chat owner or assigned specialist may upload
    is_owner = chat.user_id == user.id
    is_specialist = chat.specialist_id == user.id
    if not (is_owner or is_specialist):
        raise HTTPException(
            status_code=403, detail="Not authorised to upload to this chat")

    dest_dir = UPLOAD_DIR / str(chat_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / (file.filename or "upload")

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the 3 MB limit ({len(contents) // 1024} KB uploaded).",
        )

    existing_count = db.query(FileAttachment).filter(
        FileAttachment.chat_id == chat_id).count()
    if existing_count >= MAX_FILES_PER_CHAT:
        raise HTTPException(
            status_code=422,
            detail=f"Chat already has {existing_count} files. Maximum is {MAX_FILES_PER_CHAT}.",
        )

    dest_path.write_bytes(contents)

    attachment = FileAttachment(
        filename=file.filename or "upload",
        file_path=str(dest_path),
        file_type=file.content_type,
        file_size=len(contents),
        chat_id=chat_id,
        uploader_id=user.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    audit_repository.log(
        db,
        user_id=user.id,
        action="UPLOAD_FILE",
        details=f"Uploaded {file.filename} to chat {chat_id}",
    )
    await cache.delete_pattern(
        cache_keys.chat_detail_pattern(chat_id), user_id=user.id, resource="chat_detail"
    )
    await cache.delete_pattern(
        cache_keys.chat_list_pattern(chat.user_id), user_id=chat.user_id, resource="chat_list"
    )

    return FileAttachmentResponse(
        id=attachment.id,
        filename=attachment.filename,
        file_type=attachment.file_type,
        file_size=attachment.file_size,
        created_at=attachment.created_at.isoformat() if attachment.created_at else "",
    )


# ---------------------------------------------------------------------------
# Send message
# ---------------------------------------------------------------------------


def _generate_ai_response_task(chat_id: int, user_id: int, content: str) -> None:
    db = SessionLocal()
    try:
        _generate_ai_response(db, chat_id, user_id, content)
    finally:
        db.close()


def _generate_ai_response(db: Session, chat_id: int, user_id: int, content: str) -> None:
    try:
        chat = chat_repository.get(db, chat_id)
        if not chat:
            return

        ctx = chat.patient_context or {}
        patient_context = {
            **ctx,
            **({"specialty": chat.specialty} if chat.specialty else {}),
            **({"severity": chat.severity} if chat.severity else {}),
        } or None

        file_texts = []
        for attachment in (chat.files or []):
            text = _extract_text(attachment.file_path, attachment.file_type)
            if text.strip():
                file_texts.append(f"[{attachment.filename}]\n{text.strip()}")
        FILE_CONTEXT_CHAR_LIMIT = 8_000
        file_context = "\n\n---\n\n".join(file_texts) if file_texts else None
        if file_context and len(file_context) > FILE_CONTEXT_CHAR_LIMIT:
            file_context = file_context[:FILE_CONTEXT_CHAR_LIMIT] + \
                "\n\n[Document truncated to fit context window]"

        rag_payload: dict = {
            "query": content,
            "top_k": 4,
            "specialty": chat.specialty,
            "severity": chat.severity,
            "patient_context": patient_context,
        }
        if file_context:
            rag_payload["file_context"] = file_context

        rag_action = "RAG_ERROR"
        rag_details = f"query_len={len(content)} error=unknown"
        try:
            rag_response = httpx.post(
                f"{RAG_SERVICE_URL}/answer",
                json=rag_payload,
                timeout=RAG_REQUEST_TIMEOUT_SECONDS,
            )
            rag_response.raise_for_status()
            rag_json = rag_response.json()
            ai_content = rag_json.get("answer", "")
            # Use only citations the model actually cited; empty list means no sources shown.
            citations = rag_json.get("citations") or None
            rag_action = "RAG_ANSWER"
            rag_details = f"query_len={len(content)} top_k=4 chunks_used={len(citations) if citations else 0}"
        except Exception as exc:  # pragma: no cover - network fallback
            ai_content = (
                "RAG service unavailable right now. Echoing your question while the "
                f"service recovers: {content} (detail: {exc})"
            )
            citations = None
            rag_details = f"query_len={len(content)} error={type(exc).__name__}"

        audit_repository.log(db, user_id=user_id,
                             action=rag_action, details=rag_details)

        message_repository.create(
            db,
            chat_id=chat.id,
            content=ai_content,
            sender="ai",
            citations=citations,
        )
        cache.delete_pattern_sync(
            cache_keys.chat_detail_pattern(chat_id), user_id=user_id, resource="chat_detail"
        )
        cache.delete_pattern_sync(
            cache_keys.chat_list_pattern(chat.user_id), user_id=chat.user_id, resource="chat_list"
        )

        audit_repository.log(
            db,
            user_id=user_id,
            action="AI_RESPONSE_GENERATED",
            details=f"AI response generated for chat {chat_id}",
        )
    except Exception:
        db.rollback()
        raise


def send_message(
    db: Session,
    user: User,
    chat_id: int,
    content: str,
    background_tasks: BackgroundTasks,
) -> dict:
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # GP can only send messages before a specialist picks up the chat
    if chat.status not in (ChatStatus.OPEN, ChatStatus.SUBMITTED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send messages in {chat.status.value} state",
        )

    message_repository.create(
        db, chat_id=chat.id, content=content, sender="user")

    if chat.status == ChatStatus.OPEN:
        chat_repository.update(db, chat, status=ChatStatus.SUBMITTED)
        audit_repository.log(
            db,
            user_id=user.id,
            action="AUTO_SUBMIT_FOR_REVIEW",
            details=f"Chat {chat_id} auto-submitted after first GP message",
        )

    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat_id), user_id=user.id, resource="chat_detail"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(chat.user_id), user_id=chat.user_id, resource="chat_list"
    )

    if db.bind and db.bind.dialect.name == "sqlite":
        _generate_ai_response(db, chat.id, user.id, content)
    else:
        background_tasks.add_task(
            _generate_ai_response_task, chat.id, user.id, content)

    return {
        "status": "Message sent",
        "ai_response": f"AI response is being generated for: {content}",
        "ai_generating": True,
    }


# ---------------------------------------------------------------------------
# Submit for review
# ---------------------------------------------------------------------------


def submit_for_review(db: Session, user: User, chat_id: int) -> ChatResponse:
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.status != ChatStatus.OPEN:
        raise HTTPException(
            status_code=400,
            detail=f"Only OPEN chats can be submitted (current: {chat.status.value})",
        )

    chat = chat_repository.update(db, chat, status=ChatStatus.SUBMITTED)
    audit_repository.log(
        db,
        user_id=user.id,
        action="SUBMIT_FOR_REVIEW",
        details=f"Chat {chat_id} submitted for specialist review",
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(user.id), user_id=user.id, resource="chat_list"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat_id), user_id=user.id, resource="chat_detail"
    )
    return chat_to_response(chat)
