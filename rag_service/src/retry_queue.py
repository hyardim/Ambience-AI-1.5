from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Coroutine, Mapping
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, cast
from uuid import uuid4

from redis import Redis
from rq import Queue

from .config import (
    REDIS_URL,
    RETRY_BACKOFF_MULTIPLIER,
    RETRY_BACKOFF_SECONDS,
    RETRY_JOB_TTL_SECONDS,
    RETRY_MAX_ATTEMPTS,
)
from .generation.client import ModelGenerationError, ProviderName, generate_answer

logger = logging.getLogger("rag.retry")

QUEUE_NAME = "rag_retry"
JOB_KEY_PREFIX = "rag:job:"
IDEMPOTENCY_KEY_PREFIX = "rag:idempotency:"


class RetryJobStatus(str, Enum):
    QUEUED = "queued"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RetryValidationError(ValueError):
    """Raised when queued payload is invalid and must not be retried."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_key(job_id: str) -> str:
    return f"{JOB_KEY_PREFIX}{job_id}"


def _idempotency_key(key: str) -> str:
    return f"{IDEMPOTENCY_KEY_PREFIX}{key}"


def _serialize(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def _deserialize(value: str | bytes | None, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _decode_mapping(raw: Mapping[Any, Any]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key_raw, value_raw in raw.items():
        key = key_raw.decode("utf-8") if isinstance(key_raw, bytes) else str(key_raw)
        value = (
            value_raw.decode("utf-8")
            if isinstance(value_raw, bytes)
            else str(value_raw)
        )
        decoded[key] = value
    return decoded


def get_redis_connection() -> Redis:
    return Redis.from_url(REDIS_URL)


def get_retry_queue(connection: Redis | None = None) -> Queue:
    redis_conn = connection or get_redis_connection()
    return Queue(name=QUEUE_NAME, connection=redis_conn)


def _build_idempotency_identifier(
    idempotency_key: str | None,
    request_type: str,
    payload: dict[str, Any],
) -> str | None:
    if idempotency_key and idempotency_key.strip():
        return idempotency_key.strip()
    canonical = _serialize({"request_type": request_type, "payload": payload})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compute_backoff_seconds(attempt_count: int) -> int:
    exponent = max(attempt_count - 1, 0)
    seconds = RETRY_BACKOFF_SECONDS * (RETRY_BACKOFF_MULTIPLIER**exponent)
    return max(int(seconds), 1)


def _initial_state(
    job_id: str,
    request_type: str,
    payload: dict[str, Any],
) -> dict[str, str]:
    now = _now_iso()
    return {
        "job_id": job_id,
        "request_type": request_type,
        "status": RetryJobStatus.QUEUED.value,
        "attempt_count": "0",
        "last_error": "",
        "response": "",
        "payload": _serialize(payload),
        "created_at": now,
        "updated_at": now,
    }


def _update_job_state(
    connection: Redis,
    job_id: str,
    **fields: str,
) -> None:
    key = _job_key(job_id)
    payload = {**fields, "updated_at": _now_iso()}
    connection.hset(key, mapping=payload)
    connection.expire(key, RETRY_JOB_TTL_SECONDS)


def create_retry_job(
    *,
    request_type: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
    connection: Redis | None = None,
) -> tuple[str, RetryJobStatus]:
    redis_conn = connection or get_redis_connection()
    queue = get_retry_queue(redis_conn)
    id_key = _build_idempotency_identifier(idempotency_key, request_type, payload)

    if id_key:
        tentative_job_id = str(uuid4())
        created = redis_conn.set(
            _idempotency_key(id_key),
            tentative_job_id,
            ex=RETRY_JOB_TTL_SECONDS,
            nx=True,
        )
        if not created:
            stored_job_id = cast(
                str | bytes | None, redis_conn.get(_idempotency_key(id_key))
            )
            if stored_job_id:
                existing_job_id = (
                    stored_job_id.decode("utf-8")
                    if isinstance(stored_job_id, bytes)
                    else stored_job_id
                )
                existing = get_retry_job(existing_job_id, connection=redis_conn)
                if existing:
                    return existing_job_id, RetryJobStatus(existing["status"])
            job_id = str(uuid4())
            redis_conn.set(
                _idempotency_key(id_key),
                job_id,
                ex=RETRY_JOB_TTL_SECONDS,
            )
        else:
            job_id = tentative_job_id
    else:
        job_id = str(uuid4())

    redis_conn.hset(
        _job_key(job_id),
        mapping=_initial_state(job_id, request_type, payload),
    )
    redis_conn.expire(_job_key(job_id), RETRY_JOB_TTL_SECONDS)

    queue.enqueue("src.retry_queue.process_retry_job", job_id=job_id)
    logger.info(
        "retry_enqueue job_id=%s request_type=%s attempt=0",
        job_id,
        request_type,
    )
    return job_id, RetryJobStatus.QUEUED


def get_retry_job(
    job_id: str, connection: Redis | None = None
) -> dict[str, Any] | None:
    redis_conn = connection or get_redis_connection()
    raw = cast(Mapping[Any, Any], redis_conn.hgetall(_job_key(job_id)))
    if not raw:
        return None

    data = _decode_mapping(raw)
    data["attempt_count"] = int(data.get("attempt_count", "0"))
    data["response"] = _deserialize(data.get("response"), default=None)
    data["payload"] = _deserialize(data.get("payload"), default=None)
    return data


def _run_async(coro: Coroutine[Any, Any, str]) -> str:
    return asyncio.run(coro)


_CITATION_RE = re.compile(r"\[[\d,\s\-]+\]")


def _parse_citation_group(raw: str) -> list[int]:
    numbers: list[int] = []
    for part in raw.split(","):
        token = part.strip()
        if "-" in token:
            try:
                start_str, end_str = token.split("-", 1)
                start, end = int(start_str), int(end_str)
                numbers.extend(range(start, end + 1))
            except ValueError:
                continue
            continue
        try:
            numbers.append(int(token))
        except ValueError:
            continue
    return numbers


def _extract_citation_indices(text: str) -> set[int]:
    return {
        n
        for match in _CITATION_RE.findall(text)
        for n in _parse_citation_group(match[1:-1])
    }


def _rewrite_citations(text: str, renumber_map: dict[int, int]) -> str:
    def _rewrite(match: re.Match) -> str:
        numbers = _parse_citation_group(match.group(0)[1:-1])
        kept = sorted({renumber_map[n] for n in numbers if n in renumber_map})
        return f"[{', '.join(str(k) for k in kept)}]" if kept else ""

    return _CITATION_RE.sub(_rewrite, text)


def _select_citations(
    answer_text: str,
    citations_retrieved: list[dict[str, Any]],
    strip_references: bool,
) -> tuple[str, list[dict[str, Any]]]:
    used_indices = _extract_citation_indices(answer_text)
    sorted_used = sorted(i for i in used_indices if 1 <= i <= len(citations_retrieved))
    citations_used = [citations_retrieved[i - 1] for i in sorted_used]
    renumber_map = {original: new for new, original in enumerate(sorted_used, start=1)}
    rewritten = _rewrite_citations(answer_text, renumber_map)
    if strip_references:
        rewritten = re.sub(
            r"\n+\s*References?:.*",
            "",
            rewritten,
            flags=re.DOTALL | re.IGNORECASE,
        ).rstrip()
    return rewritten, citations_used


def _build_answer_response(
    *,
    answer_text: str,
    prompt_label: str,
    citations_retrieved: list[dict[str, Any]],
) -> dict[str, Any]:
    rewritten_answer, citations_used = _select_citations(
        answer_text,
        citations_retrieved,
        strip_references=True,
    )
    answer = (
        f"[Prompt: {prompt_label}]\n\n{rewritten_answer}"
        if prompt_label
        else rewritten_answer
    )
    return {
        "answer": answer,
        "citations_used": citations_used,
        "citations_retrieved": citations_retrieved,
        "citations": citations_used,
    }


def _build_revise_response(
    *,
    answer_text: str,
    citations_retrieved: list[dict[str, Any]],
) -> dict[str, Any]:
    rewritten_answer, citations_used = _select_citations(
        answer_text,
        citations_retrieved,
        strip_references=False,
    )
    return {
        "answer": rewritten_answer,
        "citations_used": citations_used,
        "citations_retrieved": citations_retrieved,
        "citations": citations_used,
    }


def _extract_retry_payload(
    payload: dict[str, Any],
) -> tuple[str, ProviderName, int, list[dict[str, Any]], str | None]:
    prompt = payload.get("prompt")
    provider = payload.get("provider")
    max_tokens = payload.get("max_tokens")
    citations_retrieved = payload.get("citations_retrieved") or []
    prompt_label = payload.get("prompt_label")

    if not isinstance(prompt, str) or not prompt.strip():
        raise RetryValidationError("Missing prompt for retry job")
    if provider not in {"local", "cloud"}:
        raise RetryValidationError("Invalid provider for retry job")
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        raise RetryValidationError("Invalid max_tokens for retry job")

    return (
        prompt,
        cast(ProviderName, provider),
        max_tokens,
        cast(list[dict[str, Any]], citations_retrieved),
        cast(str | None, prompt_label),
    )


def process_retry_job(job_id: str) -> None:
    redis_conn = get_redis_connection()
    state = get_retry_job(job_id, connection=redis_conn)
    if not state:
        logger.warning("retry_job_missing job_id=%s", job_id)
        return

    status = state.get("status")
    if status in {RetryJobStatus.SUCCEEDED.value, RetryJobStatus.FAILED.value}:
        logger.info("retry_skip_terminal job_id=%s status=%s", job_id, status)
        return

    payload = state.get("payload") or {}
    request_type = state.get("request_type", "answer")
    next_attempt = int(state.get("attempt_count", 0)) + 1

    _update_job_state(
        redis_conn,
        job_id,
        status=RetryJobStatus.RETRYING.value,
        attempt_count=str(next_attempt),
    )
    logger.info("retry_attempt job_id=%s attempt=%s", job_id, next_attempt)

    try:
        prompt, provider, max_tokens, citations_retrieved, prompt_label = (
            _extract_retry_payload(payload)
        )
        answer_text = _run_async(
            generate_answer(prompt, max_tokens=max_tokens, provider=provider)
        )

        if request_type == "revise":
            response = _build_revise_response(
                answer_text=answer_text,
                citations_retrieved=citations_retrieved,
            )
        else:
            response = _build_answer_response(
                answer_text=answer_text,
                prompt_label=prompt_label or "",
                citations_retrieved=citations_retrieved,
            )

        _update_job_state(
            redis_conn,
            job_id,
            status=RetryJobStatus.SUCCEEDED.value,
            response=_serialize(response),
            last_error="",
        )
        logger.info("retry_success job_id=%s attempt=%s", job_id, next_attempt)
    except RetryValidationError as exc:
        _update_job_state(
            redis_conn,
            job_id,
            status=RetryJobStatus.FAILED.value,
            last_error=str(exc),
        )
        logger.info(
            "retry_non_retryable job_id=%s attempt=%s error=%s",
            job_id,
            next_attempt,
            exc,
        )
    except ModelGenerationError as exc:
        last_error = str(exc)
        retryable = exc.retryable

        if retryable and next_attempt < RETRY_MAX_ATTEMPTS:
            backoff = _compute_backoff_seconds(next_attempt)
            queue = get_retry_queue(redis_conn)
            queue.enqueue_in(
                timedelta(seconds=backoff),
                "src.retry_queue.process_retry_job",
                job_id=job_id,
            )
            _update_job_state(
                redis_conn,
                job_id,
                status=RetryJobStatus.QUEUED.value,
                last_error=last_error,
            )
            logger.info(
                "retry_requeue job_id=%s attempt=%s backoff_seconds=%s error=%s",
                job_id,
                next_attempt,
                backoff,
                last_error,
            )
            return

        _update_job_state(
            redis_conn,
            job_id,
            status=RetryJobStatus.FAILED.value,
            last_error=last_error,
        )
        logger.info(
            "retry_permanent_failure job_id=%s attempt=%s retryable=%s error=%s",
            job_id,
            next_attempt,
            retryable,
            last_error,
        )
    except Exception as exc:
        _update_job_state(
            redis_conn,
            job_id,
            status=RetryJobStatus.FAILED.value,
            last_error=str(exc),
        )
        logger.exception(
            "retry_unexpected_failure job_id=%s attempt=%s", job_id, next_attempt
        )
