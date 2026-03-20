from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.core.config import settings
from src.db.models import Chat, Message

FILE_CONTEXT_CHAR_LIMIT = settings.FILE_CONTEXT_CHAR_LIMIT
CHAT_HISTORY_MESSAGE_LIMIT = settings.CHAT_HISTORY_MESSAGE_LIMIT
FILE_CONTEXT_TRUNCATION_NOTICE = "[Document truncated to fit context window]"


@dataclass(frozen=True)
class FileContextBuildResult:
    file_context: str | None
    was_truncated: bool = False


def extract_text(file_path: str, file_type: Optional[str]) -> str:
    """Extract plain text from an uploaded file (PDF or plain text)."""
    try:
        if file_type and "pdf" in file_type.lower():
            from pypdf import PdfReader  # lazy import — only used when PDF is uploaded

            reader = PdfReader(file_path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        return Path(file_path).read_text(errors="replace")
    except Exception:
        return ""


def build_conversation_history_from_messages(
    messages: list[Message],
    *,
    limit: int = CHAT_HISTORY_MESSAGE_LIMIT,
) -> str | None:
    if not messages:
        return None

    history_lines: list[str] = []
    for message in messages[-limit:]:
        if not message.content:
            continue
        speaker = {
            "user": "GP",
            "specialist": "Specialist",
            "ai": "AI",
        }.get(message.sender, message.sender.title())
        history_lines.append(f"{speaker}: {message.content.strip()}")

    return "\n".join(history_lines) if history_lines else None


def build_patient_context(chat: Chat, messages: list[Message]) -> dict | None:
    ctx = chat.patient_context or {}
    patient_context = {
        **ctx,
        **({"specialty": chat.specialty} if chat.specialty else {}),
        **({"severity": chat.severity} if chat.severity else {}),
    } or None
    conversation_history = build_conversation_history_from_messages(messages)
    if patient_context is None:
        patient_context = {}
    if conversation_history:
        patient_context["conversation_history"] = conversation_history
    return patient_context or None


def build_file_context(
    chat: Chat,
    *,
    extract_text_fn=extract_text,
) -> str | None:
    return build_file_context_result(chat, extract_text_fn=extract_text_fn).file_context


def build_file_context_result(
    chat: Chat,
    *,
    extract_text_fn=extract_text,
) -> FileContextBuildResult:
    file_texts: list[str] = []
    for attachment in chat.files or []:
        text = extract_text_fn(attachment.file_path, attachment.file_type)
        if text.strip():
            file_texts.append(f"[{attachment.filename}]\n{text.strip()}")
    file_context = "\n\n---\n\n".join(file_texts) if file_texts else None
    was_truncated = False
    if file_context and len(file_context) > FILE_CONTEXT_CHAR_LIMIT:
        was_truncated = True
        file_context = (
            file_context[:FILE_CONTEXT_CHAR_LIMIT]
            + f"\n\n{FILE_CONTEXT_TRUNCATION_NOTICE}"
        )
    return FileContextBuildResult(
        file_context=file_context, was_truncated=was_truncated
    )


def select_rag_citations(payload: dict) -> list | None:
    for key in ("citations_used", "citations"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return None
