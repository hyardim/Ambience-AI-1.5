from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from src.generation.client import ModelGenerationError
from src.retry_queue import (
    RetryJobStatus,
    create_retry_job,
    get_retry_job,
    process_retry_job,
)


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, dict[str, Any]]] = []
        self.enqueued_in: list[tuple[timedelta, str, dict[str, Any]]] = []

    def enqueue(self, fn_name: str, **kwargs: Any) -> None:
        self.enqueued.append((fn_name, kwargs))

    def enqueue_in(self, delay: timedelta, fn_name: str, **kwargs: Any) -> None:
        self.enqueued_in.append((delay, fn_name, kwargs))


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.kv: dict[str, str] = {}

    def hset(self, key: str, mapping: dict[str, str]) -> None:
        current = self.hashes.setdefault(key, {})
        current.update(mapping)

    def hgetall(self, key: str) -> dict[bytes, bytes]:
        item = self.hashes.get(key, {})
        return {k.encode("utf-8"): v.encode("utf-8") for k, v in item.items()}

    def expire(self, key: str, ttl: int) -> None:  # noqa: ARG002
        return

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:  # noqa: ARG002
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        return True

    def get(self, key: str) -> bytes | None:
        value = self.kv.get(key)
        if value is None:
            return None
        return value.encode("utf-8")


@pytest.fixture()
def fake_backend(monkeypatch):
    redis_conn = FakeRedis()
    queue = FakeQueue()
    monkeypatch.setattr("src.retry_queue.get_redis_connection", lambda: redis_conn)
    monkeypatch.setattr("src.retry_queue.get_retry_queue", lambda connection=None: queue)
    return redis_conn, queue


def _payload() -> dict[str, Any]:
    return {
        "prompt": "Prompt",
        "provider": "local",
        "max_tokens": 32,
        "prompt_label": "unit",
        "citations_retrieved": [
            {"text": "Evidence", "source": "S", "score": 0.9}
        ],
    }


def test_retries_on_transient_generation_error(fake_backend, monkeypatch):
    redis_conn, queue = fake_backend
    job_id, status = create_retry_job(request_type="answer", payload=_payload(), connection=redis_conn)
    assert status == RetryJobStatus.QUEUED

    async def transient_fail(*args, **kwargs):  # noqa: ANN002, ANN003
        raise ModelGenerationError("temporary", retryable=True)

    monkeypatch.setattr("src.retry_queue.generate_answer", transient_fail)

    process_retry_job(job_id)
    state = get_retry_job(job_id, connection=redis_conn)

    assert state is not None
    assert state["status"] == RetryJobStatus.QUEUED.value
    assert state["attempt_count"] == 1
    assert queue.enqueued_in


def test_no_retry_on_validation_error(fake_backend):
    redis_conn, _ = fake_backend
    payload = _payload()
    payload["max_tokens"] = 0

    job_id, _ = create_retry_job(request_type="answer", payload=payload, connection=redis_conn)
    process_retry_job(job_id)
    state = get_retry_job(job_id, connection=redis_conn)

    assert state is not None
    assert state["status"] == RetryJobStatus.FAILED.value
    assert "max_tokens" in (state["last_error"] or "")


def test_status_transitions_to_succeeded(fake_backend, monkeypatch):
    redis_conn, _ = fake_backend
    job_id, _ = create_retry_job(request_type="answer", payload=_payload(), connection=redis_conn)

    async def succeed(*args, **kwargs):  # noqa: ANN002, ANN003
        return "Answer with citation [1]"

    monkeypatch.setattr("src.retry_queue.generate_answer", succeed)

    process_retry_job(job_id)
    state = get_retry_job(job_id, connection=redis_conn)

    assert state is not None
    assert state["status"] == RetryJobStatus.SUCCEEDED.value
    assert state["attempt_count"] == 1
    assert state["response"]["citations_used"]


def test_exhausted_retries_marks_failed(fake_backend, monkeypatch):
    redis_conn, _ = fake_backend
    job_id, _ = create_retry_job(request_type="answer", payload=_payload(), connection=redis_conn)

    redis_conn.hset(f"rag:job:{job_id}", mapping={"attempt_count": "2", "status": "queued"})

    async def transient_fail(*args, **kwargs):  # noqa: ANN002, ANN003
        raise ModelGenerationError("temporary", retryable=True)

    monkeypatch.setattr("src.retry_queue.generate_answer", transient_fail)

    process_retry_job(job_id)
    state = get_retry_job(job_id, connection=redis_conn)

    assert state is not None
    assert state["status"] == RetryJobStatus.FAILED.value
    assert state["attempt_count"] == 3


def test_idempotency_key_dedup(fake_backend):
    redis_conn, queue = fake_backend
    payload = _payload()

    first_job, _ = create_retry_job(
        request_type="answer",
        payload=payload,
        idempotency_key="idem-1",
        connection=redis_conn,
    )
    second_job, _ = create_retry_job(
        request_type="answer",
        payload=payload,
        idempotency_key="idem-1",
        connection=redis_conn,
    )

    assert first_job == second_job
    assert len(queue.enqueued) == 1
