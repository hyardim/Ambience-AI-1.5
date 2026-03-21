from datetime import datetime
from typing import Any, List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from src.api.deps import get_admin_user
from src.core.config import settings
from src.db.models import User
from src.db.session import get_db
from src.schemas.admin import (
    AdminChatResponse,
    AdminStatsResponse,
    AuditLogResponse,
    RagDocumentHealth,
    RagStatusResponse,
    UserUpdateAdmin,
)
from src.schemas.auth import UserOut
from src.schemas.chat import ChatUpdate, ChatWithMessages
from src.services import admin_service
from src.services.chat_uploads import validate_upload_content
from src.services.rag_client import build_rag_headers

router = APIRouter()

_UPLOAD_CHUNK_BYTES = 64 * 1024


async def _read_upload_with_limit(file: UploadFile) -> tuple[bytes, bytes]:
    """Read upload in bounded chunks and return payload + signature sample."""
    max_size = settings.MAX_FILE_SIZE_BYTES
    total_size = 0
    signature = bytearray()
    chunks: list[bytes] = []

    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_size:
            raise HTTPException(
                status_code=413,
                detail="File exceeds the maximum allowed size.",
            )
        if len(signature) < 2048:
            remaining = 2048 - len(signature)
            signature.extend(chunk[:remaining])
        chunks.append(chunk)

    return b"".join(chunks), bytes(signature)


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=AdminStatsResponse)
def get_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return admin_service.get_stats(db)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


@router.get("/users", response_model=List[UserOut])
def list_users(
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return admin_service.list_users(db, role=role)


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return admin_service.get_user(db, user_id)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdateAdmin,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return admin_service.update_user(db, user_id, payload)


@router.delete("/users/{user_id}", response_model=UserOut)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return admin_service.deactivate_user(db, user_id)


# ---------------------------------------------------------------------------
# Chat management
# ---------------------------------------------------------------------------


@router.get("/chats", response_model=List[AdminChatResponse])
def list_all_chats(
    status: Optional[str] = None,
    specialty: Optional[str] = None,
    user_id: Optional[int] = None,
    specialist_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return admin_service.list_all_chats(
        db,
        status=status,
        specialty=specialty,
        user_id=user_id,
        specialist_id=specialist_id,
        skip=skip,
        limit=limit,
    )


@router.get("/chats/{chat_id}", response_model=ChatWithMessages)
def get_any_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return admin_service.get_any_chat(db, chat_id)


@router.patch("/chats/{chat_id}", response_model=AdminChatResponse)
def update_any_chat(
    chat_id: int,
    payload: ChatUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return admin_service.update_any_chat(db, chat_id, payload)


@router.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_any_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    admin_service.delete_any_chat(db, chat_id)


# ---------------------------------------------------------------------------
# Audit logs
# ---------------------------------------------------------------------------


@router.get("/logs", response_model=List[AuditLogResponse])
def list_audit_logs(
    action: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    user_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return admin_service.list_audit_logs(
        db,
        action=action,
        category=category,
        search=search,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Guideline upload
# ---------------------------------------------------------------------------


@router.post("/guidelines/upload")
async def upload_guideline(
    file: UploadFile = File(...),
    source_name: str = Form(...),
    _admin: User = Depends(get_admin_user),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are supported.")

    try:
        file_bytes, signature = await _read_upload_with_limit(file)
        validate_upload_content(file.filename, file.content_type, signature)
    finally:
        await file.close()

    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            rag_headers = build_rag_headers()
            request_kwargs: dict[str, Any] = {}
            if rag_headers:
                request_kwargs["headers"] = rag_headers
            response = await client.post(
                f"{settings.RAG_SERVICE_URL}/ingest",
                files={"file": (file.filename, file_bytes, "application/pdf")},
                data={"source_name": source_name},
                **request_kwargs,
            )
        except httpx.ConnectError as e:
            raise HTTPException(
                status_code=502,
                detail="RAG service is unavailable.",
            ) from e
        except httpx.TimeoutException as e:
            raise HTTPException(
                status_code=504,
                detail="Ingestion timed out. The file may be too large.",
            ) from e

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail="Guideline ingestion failed. Check RAG service logs for details.",
        )

    return response.json()


# ---------------------------------------------------------------------------
# RAG status
# ---------------------------------------------------------------------------


@router.get("/rag/status", response_model=RagStatusResponse)
async def get_rag_status(
    _admin: User = Depends(get_admin_user),
):
    rag_headers = build_rag_headers()
    request_kwargs: dict[str, Any] = {}
    if rag_headers:
        request_kwargs["headers"] = rag_headers

    service_status = "unavailable"
    documents: list[RagDocumentHealth] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            health_resp = await client.get(
                f"{settings.RAG_SERVICE_URL}/health",
                **request_kwargs,
            )
            if health_resp.status_code == 200:
                service_status = health_resp.json().get("status", "unknown")
        except (httpx.ConnectError, httpx.TimeoutException):
            pass

        try:
            docs_resp = await client.get(
                f"{settings.RAG_SERVICE_URL}/documents/health",
                **request_kwargs,
            )
            if docs_resp.status_code == 200:
                payload = docs_resp.json()
                if isinstance(payload, list):
                    documents = [
                        RagDocumentHealth.model_validate(item) for item in payload
                    ]
        except (httpx.ConnectError, httpx.TimeoutException):
            pass

    return RagStatusResponse(
        service_status=service_status,
        documents=documents,
    )
