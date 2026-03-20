from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from src.generation.client import ModelGenerationError
from src.jobs.retry import (
    RetryJobStatus,
    _build_answer_response,
    _build_idempotency_identifier,
    _build_revise_response,
    _compute_backoff_seconds,
    _decode_mapping,
    _deserialize,
    _extract_retry_payload,
    _parse_citation_group,
    _rewrite_citations,
    _select_citations,
    create_retry_job,
    get_retry_job,
    get_retry_queue,
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

    def expire(self, key: str, ttl: int) -> None:
        return

    def set(
        self, key: str, value: str, ex: int | None = None, nx: bool = False
    ) -> bool:
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        return True

    def get(self, key: str) -> bytes | None:
        value = self.kv.get(key)
        if value is None:
            return None
        return value.encode("utf-8")


@pytest.fixture
def fake_backend(monkeypatch):
    redis_conn = FakeRedis()
    queue = FakeQueue()
    monkeypatch.setattr("src.jobs.retry.get_redis_connection", lambda: redis_conn)
    monkeypatch.setattr("src.jobs.retry.get_retry_queue", lambda connection=None: queue)
    return redis_conn, queue


def _payload() -> dict[str, Any]:
    return {
        "prompt": "Prompt",
        "provider": "local",
        "max_tokens": 32,
        "prompt_label": "unit",
        "citations_retrieved": [{"text": "Evidence", "source": "S", "score": 0.9}],
    }


def test_retries_on_transient_generation_error(fake_backend, monkeypatch):
    redis_conn, queue = fake_backend
    job_id, status = create_retry_job(
        request_type="answer", payload=_payload(), connection=redis_conn
    )
    assert status == RetryJobStatus.QUEUED

    async def transient_fail(*args, **kwargs):
        raise ModelGenerationError("temporary", retryable=True)

    monkeypatch.setattr("src.jobs.retry.generate_answer", transient_fail)

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

    job_id, _ = create_retry_job(
        request_type="answer", payload=payload, connection=redis_conn
    )
    process_retry_job(job_id)
    state = get_retry_job(job_id, connection=redis_conn)

    assert state is not None
    assert state["status"] == RetryJobStatus.FAILED.value
    assert "max_tokens" in (state["last_error"] or "")


def test_status_transitions_to_succeeded(fake_backend, monkeypatch):
    redis_conn, _ = fake_backend
    job_id, _ = create_retry_job(
        request_type="answer", payload=_payload(), connection=redis_conn
    )

    async def succeed(*args, **kwargs):
        return "Answer with citation [1]"

    monkeypatch.setattr("src.jobs.retry.generate_answer", succeed)

    process_retry_job(job_id)
    state = get_retry_job(job_id, connection=redis_conn)

    assert state is not None
    assert state["status"] == RetryJobStatus.SUCCEEDED.value
    assert state["attempt_count"] == 1
    assert state["response"]["citations_used"]


def test_exhausted_retries_marks_failed(fake_backend, monkeypatch):
    redis_conn, _ = fake_backend
    job_id, _ = create_retry_job(
        request_type="answer", payload=_payload(), connection=redis_conn
    )

    redis_conn.hset(
        f"rag:job:{job_id}", mapping={"attempt_count": "2", "status": "queued"}
    )

    async def transient_fail(*args, **kwargs):
        raise ModelGenerationError("temporary", retryable=True)

    monkeypatch.setattr("src.jobs.retry.generate_answer", transient_fail)

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


def test_deserialize_handles_none_and_bytes() -> None:
    assert _deserialize(None, default="x") == "x"
    assert _deserialize(b'{"a":1}') == {"a": 1}
    assert _deserialize("not-json", default=[]) == []


def test_decode_mapping_decodes_bytes() -> None:
    raw = {b"a": b"1", "b": 2}
    assert _decode_mapping(raw) == {"a": "1", "b": "2"}


def test_build_idempotency_identifier_prefers_explicit_key() -> None:
    assert _build_idempotency_identifier(" key ", "answer", {"a": 1}) == "key"


def test_compute_backoff_seconds_never_below_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.jobs.retry.retry_config.retry_backoff_seconds", 0)
    monkeypatch.setattr("src.jobs.retry.retry_config.retry_backoff_multiplier", 0)
    assert _compute_backoff_seconds(0) == 1


def test_compute_backoff_seconds_respects_max_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.jobs.retry.retry_config.retry_backoff_seconds", 100)
    monkeypatch.setattr("src.jobs.retry.retry_config.retry_backoff_multiplier", 10)
    monkeypatch.setattr("src.jobs.retry.retry_config.retry_max_backoff_seconds", 250)
    assert _compute_backoff_seconds(4) == 250


def test_parse_citation_group_handles_ranges_and_invalid_tokens() -> None:
    assert _parse_citation_group("1, 3-4, nope, 7-") == [1, 3, 4]


def test_rewrite_and_select_citations() -> None:
    answer, citations = _select_citations(
        "Answer [2, 1]\nReferences: hidden",
        [{"id": 1}, {"id": 2}],
        strip_references=True,
    )

    assert answer == "Answer [1, 2]"
    assert citations == [{"id": 1}, {"id": 2}]
    assert _rewrite_citations("See [2]", {2: 1}) == "See [1]"


def test_build_answer_and_revise_response_shapes() -> None:
    citations = [{"id": 1}]

    answer_response = _build_answer_response(
        answer_text="Done [1]",
        prompt_label="new",
        citations_retrieved=citations,
    )
    revise_response = _build_revise_response(
        answer_text="Done [1]",
        citations_retrieved=citations,
    )

    assert answer_response["answer"].startswith("[Prompt: new]")
    assert answer_response["citations"] == citations
    assert revise_response["answer"] == "Done [1]"


def test_extract_retry_payload_validates_input() -> None:
    with pytest.raises(ValueError, match="Missing prompt"):
        _extract_retry_payload({"provider": "local", "max_tokens": 1})

    with pytest.raises(ValueError, match="Invalid provider"):
        _extract_retry_payload({"prompt": "x", "provider": "bad", "max_tokens": 1})

    with pytest.raises(ValueError, match="Invalid max_tokens"):
        _extract_retry_payload({"prompt": "x", "provider": "local", "max_tokens": 0})


def test_get_retry_job_returns_none_when_missing(fake_backend) -> None:
    redis_conn, _ = fake_backend
    assert get_retry_job("missing", connection=redis_conn) is None


def test_get_retry_queue_uses_existing_connection(fake_backend) -> None:
    redis_conn, _ = fake_backend
    queue = get_retry_queue(redis_conn)
    assert queue.connection is redis_conn


def test_get_retry_queue_applies_queue_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class DummyQueue:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("src.jobs.retry.Queue", DummyQueue)

    queue = get_retry_queue(connection="redis-conn")

    assert isinstance(queue, DummyQueue)
    assert captured["connection"] == "redis-conn"
    assert captured["default_timeout"] > 0
    assert captured["result_ttl"] >= 0
    assert captured["failure_ttl"] > 0


def test_get_redis_connection_uses_config(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class DummyRedis:
        @staticmethod
        def from_url(url: str) -> str:
            calls.append(url)
            return "redis-conn"

    monkeypatch.setattr("src.jobs.retry.Redis", DummyRedis)

    from src.jobs.retry import get_redis_connection

    assert get_redis_connection() == "redis-conn"
    assert calls


def test_process_retry_job_returns_when_job_missing(fake_backend) -> None:
    process_retry_job("missing")


def test_process_retry_job_returns_for_terminal_status(fake_backend) -> None:
    redis_conn, _ = fake_backend
    job_id, _ = create_retry_job(
        request_type="answer", payload=_payload(), connection=redis_conn
    )
    redis_conn.hset(
        f"rag:job:{job_id}", mapping={"status": RetryJobStatus.SUCCEEDED.value}
    )

    process_retry_job(job_id)

    state = get_retry_job(job_id, connection=redis_conn)
    assert state is not None
    assert state["status"] == RetryJobStatus.SUCCEEDED.value


def test_create_retry_job_generates_new_job_when_existing_lookup_missing(
    fake_backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_conn, queue = fake_backend
    redis_conn.kv["rag:idempotency:idem"] = "stale-job"

    monkeypatch.setattr(
        "src.jobs.retry._build_idempotency_identifier",
        lambda idempotency_key, request_type, payload: "idem",
    )

    job_id, status = create_retry_job(
        request_type="answer",
        payload=_payload(),
        connection=redis_conn,
    )

    assert status == RetryJobStatus.QUEUED
    assert job_id != "stale-job"
    assert len(queue.enqueued) == 1


def test_create_retry_job_without_identifier_still_queues(
    fake_backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_conn, queue = fake_backend
    monkeypatch.setattr(
        "src.jobs.retry._build_idempotency_identifier",
        lambda idempotency_key, request_type, payload: None,
    )

    job_id, status = create_retry_job(
        request_type="answer",
        payload=_payload(),
        connection=redis_conn,
    )

    assert status == RetryJobStatus.QUEUED
    assert job_id
    assert len(queue.enqueued) == 1


def test_process_retry_job_marks_failed_on_unexpected_exception(
    fake_backend, monkeypatch
):
    redis_conn, _ = fake_backend
    job_id, _ = create_retry_job(
        request_type="answer", payload=_payload(), connection=redis_conn
    )

    async def explode(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr("src.jobs.retry.generate_answer", explode)

    process_retry_job(job_id)
    state = get_retry_job(job_id, connection=redis_conn)

    assert state is not None
    assert state["status"] == RetryJobStatus.FAILED.value
    assert state["last_error"] == "unexpected"


def test_process_retry_job_builds_revise_response(fake_backend, monkeypatch) -> None:
    redis_conn, _ = fake_backend
    job_id, _ = create_retry_job(
        request_type="revise",
        payload=_payload(),
        connection=redis_conn,
    )

    async def succeed(*args, **kwargs):
        return "Answer with citation [1]"

    monkeypatch.setattr("src.jobs.retry.generate_answer", succeed)

    process_retry_job(job_id)
    state = get_retry_job(job_id, connection=redis_conn)

    assert state is not None
    assert state["response"]["answer"] == "Answer with citation [1]"
