"""Backward-compatible entrypoint for the full clinical RAG service."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from . import config as app_config
from .api.app import app
from .api.citations import MAX_CITATIONS, extract_citation_results, parse_citation_group
from .api.routes import (
    clinical_query,
    fetch_document,
    generate_clinical_answer,
    get_retry_job_status,
    health_check,
    ingest_guideline,
    revise_clinical_answer,
)
from .api.schemas import (
    AnswerRequest,
    AnswerResponse,
    IngestResponse,
    QueryRequest,
    RetryAcceptedResponse,
    RetryJobResponse,
    ReviseRequest,
    SearchResult,
)
from .api.security import require_internal_api_key
from .api.services import (
    filter_chunks,
    log_route_decision,
    retrieve_chunks,
    to_search_result,
)
from .api.streaming import ndjson_done_only, streaming_generator
from .config import db_config
from .generation.client import ModelGenerationError, generate_answer
from .ingestion.web_scheduler import GuidelineSyncScheduler
from .ingestion.web_sync import GuidelineWebSync
from .jobs.retry import RetryJobStatus, create_retry_job, get_retry_job


class GuidelineSyncTriggerRequest(BaseModel):
    source_names: list[str] | None = None
    dry_run: bool = False


class GuidelineSyncStatusResponse(BaseModel):
    running: bool
    enabled: bool
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_error: str | None = None
    last_result: dict[str, Any] | None = None


def _build_sync_scheduler() -> GuidelineSyncScheduler:
    return GuidelineSyncScheduler(
        sync_service=GuidelineWebSync(),
        db_url=db_config.database_url,
        enabled=bool(getattr(app_config, "GUIDELINE_SYNC_ENABLED", False)),
        interval_minutes=int(
            getattr(app_config, "GUIDELINE_SYNC_INTERVAL_MINUTES", 10080)
        ),
        run_on_startup=bool(getattr(app_config, "GUIDELINE_SYNC_RUN_ON_STARTUP", True)),
        timeout_seconds=int(getattr(app_config, "GUIDELINE_SYNC_TIMEOUT_SECONDS", 900)),
    )


sync_scheduler = _build_sync_scheduler()


async def start_guideline_sync_scheduler() -> None:
    sync_scheduler.start()


async def stop_guideline_sync_scheduler() -> None:
    await sync_scheduler.stop()


_base_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _main_lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]:
    await start_guideline_sync_scheduler()
    try:
        async with _base_lifespan(app_instance):
            yield
    finally:
        await stop_guideline_sync_scheduler()


app.router.lifespan_context = _main_lifespan


@app.post("/guidelines/sync", dependencies=[Depends(require_internal_api_key)])
async def trigger_guideline_sync(
    payload: GuidelineSyncTriggerRequest | None = None,
) -> dict[str, Any]:
    request = payload or GuidelineSyncTriggerRequest()
    try:
        result = await sync_scheduler.trigger_once(
            source_names=set(request.source_names) if request.source_names else None,
            dry_run=request.dry_run,
        )
        return {"status": "ok", **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/guidelines/sync/status",
    response_model=GuidelineSyncStatusResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def guideline_sync_status() -> GuidelineSyncStatusResponse:
    return GuidelineSyncStatusResponse(**sync_scheduler.status())


__all__ = [
    "MAX_CITATIONS",
    "AnswerRequest",
    "AnswerResponse",
    "GuidelineSyncStatusResponse",
    "GuidelineSyncTriggerRequest",
    "IngestResponse",
    "ModelGenerationError",
    "QueryRequest",
    "RetryAcceptedResponse",
    "RetryJobResponse",
    "RetryJobStatus",
    "ReviseRequest",
    "SearchResult",
    "_main_lifespan",
    "app",
    "clinical_query",
    "create_retry_job",
    "extract_citation_results",
    "fetch_document",
    "filter_chunks",
    "generate_answer",
    "generate_clinical_answer",
    "get_retry_job",
    "get_retry_job_status",
    "guideline_sync_status",
    "health_check",
    "ingest_guideline",
    "log_route_decision",
    "ndjson_done_only",
    "parse_citation_group",
    "retrieve_chunks",
    "revise_clinical_answer",
    "start_guideline_sync_scheduler",
    "stop_guideline_sync_scheduler",
    "streaming_generator",
    "sync_scheduler",
    "to_search_result",
    "trigger_guideline_sync",
]
