from __future__ import annotations

import pytest

import src.main as main


@pytest.mark.anyio
async def test_trigger_guideline_sync_returns_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeScheduler:
        async def trigger_once(self, **kwargs: object) -> dict[str, object]:
            assert kwargs["dry_run"] is True
            assert kwargs["source_names"] == {"NICE"}
            return {
                "started_at": "start",
                "finished_at": "end",
                "summary": {
                    "discovered_count": 3,
                    "downloaded_new_count": 1,
                    "downloaded_updated_count": 1,
                    "skipped_unchanged_count": 1,
                    "ingest_succeeded_count": 2,
                    "ingest_failed_count": 0,
                    "errors": [],
                },
            }

        def status(self) -> dict[str, object]:
            return {
                "running": False,
                "enabled": False,
                "last_started_at": None,
                "last_finished_at": None,
                "last_error": None,
                "last_result": None,
            }

    monkeypatch.setattr(main, "sync_scheduler", FakeScheduler())

    response = await main.trigger_guideline_sync(
        main.GuidelineSyncTriggerRequest(source_names=["NICE"], dry_run=True)
    )

    assert response["status"] == "ok"
    assert response["summary"]["discovered_count"] == 3


@pytest.mark.anyio
async def test_guideline_sync_status_route(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeScheduler:
        async def trigger_once(self, **kwargs: object) -> dict[str, object]:
            del kwargs
            return {}

        def status(self) -> dict[str, object]:
            return {
                "running": True,
                "enabled": True,
                "last_started_at": "start",
                "last_finished_at": "end",
                "last_error": None,
                "last_result": {"summary": {"discovered_count": 1}},
            }

    monkeypatch.setattr(main, "sync_scheduler", FakeScheduler())

    status = await main.guideline_sync_status()

    assert status.running is True
    assert status.enabled is True
    assert status.last_result["summary"]["discovered_count"] == 1
