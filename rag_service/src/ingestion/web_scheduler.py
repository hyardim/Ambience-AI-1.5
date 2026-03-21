from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from ..utils.logger import setup_logger
from .web_sync import GuidelineWebSync, SyncAlreadyRunningError

logger = setup_logger(__name__)


class GuidelineSyncScheduler:
    def __init__(
        self,
        *,
        sync_service: GuidelineWebSync,
        db_url: str,
        enabled: bool,
        interval_minutes: int,
        run_on_startup: bool,
        timeout_seconds: int,
    ) -> None:
        self._sync_service = sync_service
        self._db_url = db_url
        self._enabled = enabled
        self._interval_seconds = max(60, interval_minutes * 60)
        self._run_on_startup = run_on_startup
        self._timeout_seconds = max(30, timeout_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._status: dict[str, Any] = {
            "running": False,
            "enabled": enabled,
            "last_started_at": None,
            "last_finished_at": None,
            "last_error": None,
            "last_result": None,
        }

    def start(self) -> None:
        if not self._enabled:
            logger.info("sync.scheduler.disabled")
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("sync.scheduler.started interval_seconds=%s", self._interval_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None
        logger.info("sync.scheduler.stopped")

    async def trigger_once(
        self,
        *,
        source_names: set[str] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        self._status["last_started_at"] = datetime.now(timezone.utc).isoformat()
        self._status["running"] = True
        self._status["last_error"] = None
        logger.info("sync.run.start source_filter=%s dry_run=%s", source_names, dry_run)
        try:
            result = await asyncio.wait_for(
                self._sync_service.sync_once(
                    db_url=self._db_url,
                    source_names=source_names,
                    dry_run=dry_run,
                    timeout_seconds=self._timeout_seconds,
                ),
                timeout=self._timeout_seconds,
            )
            self._status["last_result"] = result
            return result
        except SyncAlreadyRunningError as exc:
            self._status["last_error"] = str(exc)
            return {
                "started_at": self._status["last_started_at"],
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "discovered_count": 0,
                    "downloaded_new_count": 0,
                    "downloaded_updated_count": 0,
                    "skipped_unchanged_count": 0,
                    "ingest_succeeded_count": 0,
                    "ingest_failed_count": 0,
                    "errors": [str(exc)],
                },
            }
        except Exception as exc:
            self._status["last_error"] = str(exc)
            logger.exception("sync.run.error error=%s", exc)
            return {
                "started_at": self._status["last_started_at"],
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "discovered_count": 0,
                    "downloaded_new_count": 0,
                    "downloaded_updated_count": 0,
                    "skipped_unchanged_count": 0,
                    "ingest_succeeded_count": 0,
                    "ingest_failed_count": 0,
                    "errors": [str(exc)],
                },
            }
        finally:
            self._status["last_finished_at"] = datetime.now(timezone.utc).isoformat()
            self._status["running"] = False
            logger.info(
                "sync.run.end last_error=%s",
                self._status["last_error"],
            )

    def status(self) -> dict[str, Any]:
        combined = dict(self._status)
        service_status = self._sync_service.last_status()
        combined["running"] = bool(combined["running"] or service_status["running"])
        if combined["last_result"] is None:
            combined["last_result"] = service_status.get("last_run")
        return combined

    async def _run_loop(self) -> None:
        if self._run_on_startup:
            await self.trigger_once()

        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                await self.trigger_once()
