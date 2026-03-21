from __future__ import annotations

import asyncio

from src.ingestion.web_scheduler import GuidelineSyncScheduler
from src.ingestion.web_sync import SyncAlreadyRunningError


class _LockedSyncService:
    def __init__(self) -> None:
        self.running = False
        self.calls = 0

    async def sync_once(self, **kwargs):
        if self.running:
            raise SyncAlreadyRunningError("Guideline sync already running")
        self.running = True
        self.calls += 1
        await asyncio.sleep(0.05)
        self.running = False
        return {
            "started_at": "start",
            "finished_at": "end",
            "summary": {
                "discovered_count": 1,
                "downloaded_new_count": 0,
                "downloaded_updated_count": 0,
                "skipped_unchanged_count": 1,
                "ingest_succeeded_count": 0,
                "ingest_failed_count": 0,
                "errors": [],
            },
        }

    def last_status(self):
        return {"running": self.running, "last_run": None}


def test_scheduler_prevents_overlapping_runs() -> None:
    scheduler = GuidelineSyncScheduler(
        sync_service=_LockedSyncService(),
        db_url="postgresql://localhost/test",
        enabled=False,
        interval_minutes=60,
        run_on_startup=False,
        timeout_seconds=60,
    )

    async def run_two():
        first = asyncio.create_task(scheduler.trigger_once())
        await asyncio.sleep(0.01)
        second = asyncio.create_task(scheduler.trigger_once())
        return await asyncio.gather(first, second)

    results = asyncio.run(run_two())
    errors = [result["summary"]["errors"] for result in results]
    assert any("already running" in " ".join(err).lower() for err in errors)


def test_scheduler_status_includes_last_result() -> None:
    scheduler = GuidelineSyncScheduler(
        sync_service=_LockedSyncService(),
        db_url="postgresql://localhost/test",
        enabled=False,
        interval_minutes=60,
        run_on_startup=False,
        timeout_seconds=60,
    )

    asyncio.run(scheduler.trigger_once())
    status = scheduler.status()
    assert status["last_result"] is not None
    assert status["enabled"] is False


class _StatusOnlyService:
    async def sync_once(self, **kwargs):
        del kwargs
        return {"summary": {"errors": []}}

    def last_status(self):
        return {"running": True, "last_run": {"summary": {"ok": True}}}


def test_scheduler_status_merges_running_from_service() -> None:
    scheduler = GuidelineSyncScheduler(
        sync_service=_StatusOnlyService(),
        db_url="postgresql://localhost/test",
        enabled=False,
        interval_minutes=60,
        run_on_startup=False,
        timeout_seconds=60,
    )

    status = scheduler.status()
    assert status["running"] is True
    assert status["last_result"] == {"summary": {"ok": True}}


def test_scheduler_stop_is_noop_without_task() -> None:
    scheduler = GuidelineSyncScheduler(
        sync_service=_StatusOnlyService(),
        db_url="postgresql://localhost/test",
        enabled=True,
        interval_minutes=60,
        run_on_startup=False,
        timeout_seconds=60,
    )
    asyncio.run(scheduler.stop())


def test_scheduler_start_and_stop_lifecycle() -> None:
    scheduler = GuidelineSyncScheduler(
        sync_service=_StatusOnlyService(),
        db_url="postgresql://localhost/test",
        enabled=True,
        interval_minutes=60,
        run_on_startup=False,
        timeout_seconds=60,
    )

    async def run_lifecycle() -> None:
        scheduler.start()
        first_task = scheduler._task
        scheduler.start()
        assert scheduler._task is first_task
        assert first_task is not None
        scheduler._stop_event.set()
        await scheduler.stop()
        assert scheduler._task is None

    asyncio.run(run_lifecycle())


def test_scheduler_run_loop_handles_timeout_and_triggers_periodic_run(
    monkeypatch,
) -> None:
    scheduler = GuidelineSyncScheduler(
        sync_service=_StatusOnlyService(),
        db_url="postgresql://localhost/test",
        enabled=True,
        interval_minutes=60,
        run_on_startup=True,
        timeout_seconds=60,
    )
    scheduler._interval_seconds = 0.01
    calls = {"count": 0}

    async def fake_trigger_once(*, source_names=None, dry_run=False):
        del source_names, dry_run
        calls["count"] += 1
        if calls["count"] >= 2:
            scheduler._stop_event.set()
        return {"summary": {"errors": []}}

    monkeypatch.setattr(scheduler, "trigger_once", fake_trigger_once)
    asyncio.run(scheduler._run_loop())
    assert calls["count"] >= 2


def test_scheduler_start_disabled_is_noop() -> None:
    scheduler = GuidelineSyncScheduler(
        sync_service=_StatusOnlyService(),
        db_url="postgresql://localhost/test",
        enabled=False,
        interval_minutes=60,
        run_on_startup=False,
        timeout_seconds=60,
    )
    scheduler.start()
    assert scheduler._task is None


def test_scheduler_trigger_once_handles_generic_exception() -> None:
    class _BoomService:
        async def sync_once(self, **kwargs):
            del kwargs
            raise RuntimeError("boom")

        def last_status(self):
            return {"running": False, "last_run": None}

    scheduler = GuidelineSyncScheduler(
        sync_service=_BoomService(),
        db_url="postgresql://localhost/test",
        enabled=True,
        interval_minutes=60,
        run_on_startup=False,
        timeout_seconds=60,
    )
    result = asyncio.run(scheduler.trigger_once())
    assert "boom" in result["summary"]["errors"][0]
