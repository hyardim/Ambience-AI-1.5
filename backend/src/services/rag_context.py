from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.core.config import settings
from src.db.models import Chat, Message

FILE_CONTEXT_CHAR_LIMIT = settings.FILE_CONTEXT_CHAR_LIMIT
CHAT_HISTORY_MESSAGE_LIMIT = settings.CHAT_HISTORY_MESSAGE_LIMIT
FILE_CONTEXT_TRUNCATION_NOTICE = "[Document truncated to fit context window]"
# Approximate token budget for conversation history.  One "token" is roughly
# 4 characters, so 2000 tokens ~= 8000 characters.
CHAT_HISTORY_TOKEN_BUDGET = 2000
_CHARS_PER_TOKEN_ESTIMATE = 4


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
            extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
            if not extracted or len(extracted.strip()) < 50:
                return (
                    "\u26a0\ufe0f This PDF appears to be empty, password-protected, "
                    "or contains only images. No text could be extracted."
                )
            return extracted
        return Path(file_path).read_text(errors="replace")
    except Exception:
        return ""


def build_conversation_history_from_messages(
    messages: list[Message],
    *,
    limit: int = CHAT_HISTORY_MESSAGE_LIMIT,
    token_budget: int = CHAT_HISTORY_TOKEN_BUDGET,
) -> str | None:
    """Build a newline-delimited conversation transcript from recent messages.

    The result is truncated to stay within *token_budget* estimated tokens
    (using a simple chars / 4 heuristic).  The most recent messages are kept
    when the history exceeds the budget.
    """
    if not messages:
        return None

    char_budget = token_budget * _CHARS_PER_TOKEN_ESTIMATE

    history_lines: list[str] = []
    total_chars = 0
    # Walk backwards from the most recent message so we keep the tail while
    # ignoring any persisted fallback/error AI messages.
    for message in reversed(messages[-limit:]):
        if (
            not message.content
            or getattr(message, "is_error", False)
            or message.sender == "ai"
        ):
            continue
        speaker = {
            "user": "GP",
            "specialist": "Specialist",
            "ai": "AI",
        }.get(message.sender, message.sender.title())
        line = f"{speaker}: {message.content.strip()}"
        line_chars = len(line) + 1  # +1 for the joining newline
        if total_chars + line_chars > char_budget and history_lines:
            break
        history_lines.append(line)
        total_chars += line_chars

    # Reverse back to chronological order.
    history_lines.reverse()
    return "\n".join(history_lines) if history_lines else None


def build_patient_context(chat: Chat, messages: list[Message]) -> dict | None:
    ctx = chat.patient_context or {}
    patient_context = {
        **ctx,
        **({"specialty": chat.specialty} if chat.specialty else {}),
    } or None
    if patient_context is None:
        patient_context = {}
    if settings.RAG_INCLUDE_CONVERSATION_HISTORY:
        conversation_history = build_conversation_history_from_messages(messages)
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
        # Try to cut at the last sentence boundary (". ") before the limit,
        # falling back to the last word boundary (space) to avoid mid-word cuts.
        truncated = file_context[:FILE_CONTEXT_CHAR_LIMIT]
        sentence_end = truncated.rfind(". ")
        if sentence_end > FILE_CONTEXT_CHAR_LIMIT // 2:
            truncated = truncated[: sentence_end + 1]  # include the period
        else:
            word_end = truncated.rfind(" ")
            if word_end > FILE_CONTEXT_CHAR_LIMIT // 2:
                truncated = truncated[:word_end]
        file_context = truncated + f"\n\n{FILE_CONTEXT_TRUNCATION_NOTICE}"
    return FileContextBuildResult(
        file_context=file_context, was_truncated=was_truncated
    )


def select_rag_citations(payload: dict) -> list | None:
    first_empty_list: list | None = None
    for key in ("citations_used", "citations", "citations_retrieved"):
        value = payload.get(key)
        if isinstance(value, list):
            if value:
                return value
            if first_empty_list is None:
                first_empty_list = value
    return first_empty_list
