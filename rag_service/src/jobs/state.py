from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from ..config import retry_config

JOB_KEY_PREFIX = "rag:job:"
IDEMPOTENCY_KEY_PREFIX = "rag:idempotency:"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_key(job_id: str) -> str:
    return f"{JOB_KEY_PREFIX}{job_id}"


def idempotency_key(key: str) -> str:
    return f"{IDEMPOTENCY_KEY_PREFIX}{key}"


def serialize(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def deserialize(value: str | bytes | None, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def decode_mapping(raw: dict[Any, Any]) -> dict[str, Any]:
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


def build_idempotency_identifier(
    idempotency_key_value: str | None,
    request_type: str,
    payload: dict[str, Any],
) -> str | None:
    if idempotency_key_value and idempotency_key_value.strip():
        return idempotency_key_value.strip()
    canonical = serialize({"request_type": request_type, "payload": payload})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_backoff_seconds(attempt_count: int) -> int:
    exponent = max(attempt_count - 1, 0)
    seconds = retry_config.retry_backoff_seconds * (
        retry_config.retry_backoff_multiplier**exponent
    )
    capped = min(int(seconds), retry_config.retry_max_backoff_seconds)
    return max(capped, 1)


def update_job_state(connection: Any, job_id: str, **fields: str) -> None:
    connection.hset(job_key(job_id), mapping={**fields, "updated_at": now_iso()})
    connection.expire(job_key(job_id), retry_config.retry_job_ttl_seconds)
