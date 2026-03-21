from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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


@pytest.mark.anyio
async def test_scheduler_lifecycle_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeScheduler:
        started = 0
        stopped = 0

        def start(self) -> None:
            self.started += 1

        async def stop(self) -> None:
            self.stopped += 1

        async def trigger_once(self, **kwargs: object) -> dict[str, object]:
            del kwargs
            return {}

        def status(self) -> dict[str, object]:
            return {
                "running": False,
                "enabled": True,
                "last_started_at": None,
                "last_finished_at": None,
                "last_error": None,
                "last_result": None,
            }

    fake = FakeScheduler()
    monkeypatch.setattr(main, "sync_scheduler", fake)

    await main.start_guideline_sync_scheduler()
    await main.stop_guideline_sync_scheduler()

    assert fake.started == 1
    assert fake.stopped == 1


def test_guideline_sync_routes_require_internal_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeScheduler:
        async def trigger_once(self, **kwargs: object) -> dict[str, object]:
            del kwargs
            return {
                "started_at": "start",
                "finished_at": "end",
                "summary": {
                    "discovered_count": 0,
                    "downloaded_new_count": 0,
                    "downloaded_updated_count": 0,
                    "skipped_unchanged_count": 0,
                    "ingest_succeeded_count": 0,
                    "ingest_failed_count": 0,
                    "errors": [],
                },
            }

        def status(self) -> dict[str, object]:
            return {
                "running": False,
                "enabled": True,
                "last_started_at": None,
                "last_finished_at": None,
                "last_error": None,
                "last_result": None,
            }

        def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    monkeypatch.setattr(main, "sync_scheduler", FakeScheduler())
    monkeypatch.setenv("RAG_INTERNAL_API_KEY", "test-internal-key")

    client = TestClient(main.app, raise_server_exceptions=False)

    unauth_sync = client.post("/guidelines/sync", json={"dry_run": True})
    assert unauth_sync.status_code == 401

    auth_sync = client.post(
        "/guidelines/sync",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json={"dry_run": True},
    )
    assert auth_sync.status_code == 200

    unauth_status = client.get("/guidelines/sync/status")
    assert unauth_status.status_code == 401

    auth_status = client.get(
        "/guidelines/sync/status",
        headers={"X-Internal-API-Key": "test-internal-key"},
    )
    assert auth_status.status_code == 200
