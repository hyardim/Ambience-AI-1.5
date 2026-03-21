from __future__ import annotations

import asyncio

from src.ingestion.web_scheduler import GuidelineSyncScheduler
from src.ingestion.web_sync import SyncAlreadyRunningError


class _LockedSyncService:
    def __init__(self) -> None:
        self.running = False
        self.calls = 0

    async def sync_once(self, **kwargs):  # noqa: ANN003
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
