"""Tests for the retry worker startup script.

Verifies that the Worker is constructed correctly after removing the
deprecated `rq.Connection` context manager (removed in rq >= 1.16).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent / "scripts" / "workers" / "run_retry_worker.py"
)


@pytest.fixture(autouse=True)
def _restore_stubbed_modules_after_test() -> None:
    module_names = [
        "redis",
        "rq",
        "src.config",
        "src.jobs.retry",
        "run_retry_worker",
    ]
    originals = {name: sys.modules.get(name) for name in module_names}
    try:
        yield
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _load_worker_module(
    fake_redis_cls: MagicMock, fake_worker_cls: MagicMock
) -> ModuleType:
    """Load run_retry_worker with redis and rq stubbed out."""
    # Stub redis package
    redis_mod = ModuleType("redis")
    redis_mod.Redis = fake_redis_cls  # type: ignore[attr-defined]
    sys.modules.setdefault("redis", redis_mod)
    sys.modules["redis"].Redis = fake_redis_cls  # type: ignore[attr-defined]

    # Stub rq package
    rq_mod = ModuleType("rq")
    rq_mod.Worker = fake_worker_cls  # type: ignore[attr-defined]
    sys.modules["rq"] = rq_mod

    # Stub src.config and src.jobs.retry
    cfg_mod = ModuleType("src.config")
    cfg_mod.retry_config = ModuleType("retry_config")  # type: ignore[attr-defined]
    cfg_mod.retry_config.redis_url = "redis://localhost:6379/0"  # type: ignore[attr-defined]
    sys.modules["src.config"] = cfg_mod

    rq_src = ModuleType("src.jobs.retry")
    rq_src.QUEUE_NAME = "rag_retry"  # type: ignore[attr-defined]
    sys.modules["src.jobs.retry"] = rq_src

    # Force re-load
    sys.modules.pop("run_retry_worker", None)
    spec = importlib.util.spec_from_file_location("run_retry_worker", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_worker_receives_connection_kwarg():
    """Worker must be instantiated with connection= rather than via Connection()."""
    fake_redis_instance = MagicMock()
    fake_redis_cls = MagicMock()
    fake_redis_cls.from_url.return_value = fake_redis_instance

    fake_worker_instance = MagicMock()
    fake_worker_cls = MagicMock(return_value=fake_worker_instance)

    mod = _load_worker_module(fake_redis_cls, fake_worker_cls)
    mod.main()

    fake_worker_cls.assert_called_once()
    _, kwargs = fake_worker_cls.call_args
    assert "connection" in kwargs, "Worker must receive connection= keyword argument"
    assert kwargs["connection"] is fake_redis_instance


def test_worker_listens_on_correct_queue():
    """Worker must listen on the QUEUE_NAME ('rag_retry')."""
    fake_redis_cls = MagicMock()
    fake_redis_cls.from_url.return_value = MagicMock()
    fake_worker_instance = MagicMock()
    fake_worker_cls = MagicMock(return_value=fake_worker_instance)

    mod = _load_worker_module(fake_redis_cls, fake_worker_cls)
    mod.main()

    args, _ = fake_worker_cls.call_args
    queues = args[0]
    assert "rag_retry" in queues, "Worker must listen on queue 'rag_retry'"


def test_worker_starts_with_scheduler():
    """Worker.work() must be called with with_scheduler=True for delayed retries."""
    fake_redis_cls = MagicMock()
    fake_redis_cls.from_url.return_value = MagicMock()
    fake_worker_instance = MagicMock()
    fake_worker_cls = MagicMock(return_value=fake_worker_instance)

    mod = _load_worker_module(fake_redis_cls, fake_worker_cls)
    mod.main()

    fake_worker_instance.work.assert_called_once_with(with_scheduler=True)


def test_rq_connection_not_imported():
    """Ensure the deprecated rq.Connection is no longer present in the script."""
    source_code = _SCRIPT_PATH.read_text()
    assert "Connection" not in source_code, (
        "Deprecated rq.Connection must not be used — it was removed in rq >= 1.16"
    )


def test_worker_registers_signal_handlers(monkeypatch):
    """Worker registers SIGTERM/SIGINT handlers that trigger request_stop()."""
    fake_redis_cls = MagicMock()
    fake_redis_cls.from_url.return_value = MagicMock()
    fake_worker_instance = MagicMock()
    fake_worker_cls = MagicMock(return_value=fake_worker_instance)

    mod = _load_worker_module(fake_redis_cls, fake_worker_cls)

    captured: list[object] = []

    def fake_signal(_sig, handler):
        captured.append(handler)

    monkeypatch.setattr(mod.signal, "signal", fake_signal)
    mod.main()

    assert len(captured) == 2
    for handler in captured:
        handler(0, None)
    assert fake_worker_instance.request_stop.call_count == 2
