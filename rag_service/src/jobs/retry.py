from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, cast
from uuid import uuid4

from redis import Redis
from rq import Queue

from ..config import path_config, retry_config
from ..generation.client import (
    ModelGenerationError,
    ProviderName,
    generate_answer,
)
from ..utils.logger import setup_logger
from ..utils.telemetry import append_jsonl
from .responses import (
    build_answer_response,
    build_revise_response,
)
from .state import (
    build_idempotency_identifier,
    compute_backoff_seconds,
    decode_mapping,
    deserialize,
    serialize,
    update_job_state,
)
from .state import (
    idempotency_key as state_idempotency_key,
)
from .state import (
    job_key as state_job_key,
)

logger = setup_logger("rag.retry")
QUEUE_NAME = "rag_retry"
RETRY_TELEMETRY_PATH = path_config.logs / "retry_metrics.jsonl"


class RetryJobStatus(str, Enum):
    QUEUED = "queued"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RetryValidationError(ValueError):
    """Raised when queued payload is invalid and must not be retried."""


def _run_async(coro: Coroutine[Any, Any, str]) -> str:
    return asyncio.run(coro)


def get_redis_connection() -> Redis:
    return Redis.from_url(retry_config.redis_url)


def get_retry_queue(connection: Redis | None = None) -> Queue:
    redis_conn = connection or get_redis_connection()
    return Queue(
        name=QUEUE_NAME,
        connection=redis_conn,
        default_timeout=retry_config.retry_queue_job_timeout_seconds,
        result_ttl=retry_config.retry_queue_result_ttl_seconds,
        failure_ttl=retry_config.retry_queue_failure_ttl_seconds,
    )


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
            state_idempotency_key(id_key),
            tentative_job_id,
            ex=retry_config.retry_job_ttl_seconds,
            nx=True,
        )
        if not created:
            stored_job_id = cast(
                str | bytes | None, redis_conn.get(state_idempotency_key(id_key))
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
                state_idempotency_key(id_key),
                job_id,
                ex=retry_config.retry_job_ttl_seconds,
            )
        else:
            job_id = tentative_job_id
    else:
        job_id = str(uuid4())

    now = datetime.now(timezone.utc).isoformat()

    redis_conn.hset(
        state_job_key(job_id),
        mapping={
            "job_id": job_id,
            "request_type": request_type,
            "status": RetryJobStatus.QUEUED.value,
            "attempt_count": "0",
            "last_error": "",
            "response": "",
            "payload": serialize(payload),
            "created_at": now,
            "updated_at": now,
        },
    )
    redis_conn.expire(state_job_key(job_id), retry_config.retry_job_ttl_seconds)
    # Enqueue positional args so RQ always passes job_id into process_retry_job(job_id).
    queue.enqueue("src.jobs.retry.process_retry_job", job_id)
    append_jsonl(
        RETRY_TELEMETRY_PATH,
        {
            "event": "enqueue",
            "job_id": job_id,
            "request_type": request_type,
            "status": RetryJobStatus.QUEUED.value,
            "provider": payload.get("provider"),
        },
    )
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
    raw = cast(dict[Any, Any], redis_conn.hgetall(state_job_key(job_id)))
    if not raw:
        return None

    data = decode_mapping(raw)
    data["attempt_count"] = int(data.get("attempt_count", "0"))
    data["response"] = deserialize(data.get("response"), default=None)
    data["payload"] = deserialize(data.get("payload"), default=None)
    return data


def _mark_job_retrying(redis_conn: Redis, job_id: str, next_attempt: int) -> None:
    update_job_state(
        redis_conn,
        job_id,
        status=RetryJobStatus.RETRYING.value,
        attempt_count=str(next_attempt),
    )


def _mark_job_failed(
    redis_conn: Redis,
    job_id: str,
    *,
    last_error: str,
) -> None:
    update_job_state(
        redis_conn,
        job_id,
        status=RetryJobStatus.FAILED.value,
        last_error=last_error,
    )


def _mark_job_succeeded(
    redis_conn: Redis,
    job_id: str,
    *,
    response: dict[str, Any],
) -> None:
    update_job_state(
        redis_conn,
        job_id,
        status=RetryJobStatus.SUCCEEDED.value,
        response=serialize(response),
        last_error="",
    )


def _requeue_retry_job(
    redis_conn: Redis,
    job_id: str,
    *,
    next_attempt: int,
    last_error: str,
) -> int:
    backoff = compute_backoff_seconds(next_attempt)
    queue = get_retry_queue(redis_conn)
    queue.enqueue_in(
        timedelta(seconds=backoff),
        "src.jobs.retry.process_retry_job",
        job_id,
    )
    update_job_state(
        redis_conn,
        job_id,
        status=RetryJobStatus.QUEUED.value,
        last_error=last_error,
    )
    return backoff


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

    _mark_job_retrying(redis_conn, job_id, next_attempt)
    append_jsonl(
        RETRY_TELEMETRY_PATH,
        {
            "event": "attempt",
            "job_id": job_id,
            "request_type": request_type,
            "attempt": next_attempt,
            "status": RetryJobStatus.RETRYING.value,
        },
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
            response = build_revise_response(
                answer_text=answer_text,
                citations_retrieved=citations_retrieved,
            )
        else:
            response = build_answer_response(
                answer_text=answer_text,
                prompt_label=prompt_label or "",
                citations_retrieved=citations_retrieved,
            )

        _mark_job_succeeded(redis_conn, job_id, response=response)
        append_jsonl(
            RETRY_TELEMETRY_PATH,
            {
                "event": "success",
                "job_id": job_id,
                "request_type": request_type,
                "attempt": next_attempt,
                "status": RetryJobStatus.SUCCEEDED.value,
            },
        )
        logger.info("retry_success job_id=%s attempt=%s", job_id, next_attempt)
    except RetryValidationError as exc:
        _mark_job_failed(redis_conn, job_id, last_error=str(exc))
        append_jsonl(
            RETRY_TELEMETRY_PATH,
            {
                "event": "validation_failure",
                "job_id": job_id,
                "request_type": request_type,
                "attempt": next_attempt,
                "status": RetryJobStatus.FAILED.value,
                "error": str(exc),
            },
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

        if retryable and next_attempt < retry_config.retry_max_attempts:
            backoff = _requeue_retry_job(
                redis_conn,
                job_id,
                next_attempt=next_attempt,
                last_error=last_error,
            )
            append_jsonl(
                RETRY_TELEMETRY_PATH,
                {
                    "event": "requeue",
                    "job_id": job_id,
                    "request_type": request_type,
                    "attempt": next_attempt,
                    "status": RetryJobStatus.QUEUED.value,
                    "retryable": retryable,
                    "backoff_seconds": backoff,
                    "error": last_error,
                },
            )
            logger.info(
                "retry_requeue job_id=%s attempt=%s backoff_seconds=%s error=%s",
                job_id,
                next_attempt,
                backoff,
                last_error,
            )
            return

        _mark_job_failed(redis_conn, job_id, last_error=last_error)
        append_jsonl(
            RETRY_TELEMETRY_PATH,
            {
                "event": "permanent_failure",
                "job_id": job_id,
                "request_type": request_type,
                "attempt": next_attempt,
                "status": RetryJobStatus.FAILED.value,
                "retryable": retryable,
                "error": last_error,
            },
        )
        logger.info(
            "retry_permanent_failure job_id=%s attempt=%s retryable=%s error=%s",
            job_id,
            next_attempt,
            retryable,
            last_error,
        )
    except Exception as exc:
        last_error = str(exc)
        # Treat unexpected errors as retryable (e.g. transient Redis/network
        # failures, JSON serialization hiccups) rather than permanently
        # failing the job on the first occurrence.
        if next_attempt < retry_config.retry_max_attempts:
            backoff = _requeue_retry_job(
                redis_conn,
                job_id,
                next_attempt=next_attempt,
                last_error=last_error,
            )
            append_jsonl(
                RETRY_TELEMETRY_PATH,
                {
                    "event": "unexpected_requeue",
                    "job_id": job_id,
                    "request_type": request_type,
                    "attempt": next_attempt,
                    "status": RetryJobStatus.QUEUED.value,
                    "backoff_seconds": backoff,
                    "error": last_error,
                },
            )
            logger.warning(
                "retry_unexpected_requeue job_id=%s attempt=%s "
                "backoff_seconds=%s error=%s",
                job_id,
                next_attempt,
                backoff,
                last_error,
            )
            return

        _mark_job_failed(redis_conn, job_id, last_error=last_error)
        append_jsonl(
            RETRY_TELEMETRY_PATH,
            {
                "event": "unexpected_failure",
                "job_id": job_id,
                "request_type": request_type,
                "attempt": next_attempt,
                "status": RetryJobStatus.FAILED.value,
                "error": last_error,
            },
        )
        logger.exception(
            "retry_unexpected_failure job_id=%s attempt=%s", job_id, next_attempt
        )


_build_idempotency_identifier = build_idempotency_identifier
