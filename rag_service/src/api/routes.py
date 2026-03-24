from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..config import (
    cloud_llm_config,
    db_config,
    local_llm_config,
    path_config,
    retry_config,
    routing_config,
)
from ..generation.client import ModelGenerationError, generate_answer
from ..generation.prompts import (
    ACTIVE_PROMPT,
    build_grounded_prompt,
    build_revision_prompt,
)
from ..generation.router import select_generation_provider
from ..ingestion.pipeline import PipelineError, load_sources, run_ingestion
from ..jobs.retry import RetryJobStatus, create_retry_job, get_retry_job
from ..retrieval.vector_store import get_source_path_for_doc
from ..utils.db import db as db_manager
from ..utils.logger import setup_logger
from . import services as api_services
from .citations import MAX_CITATIONS, extract_citation_results
from .schemas import (
    AnswerRequest,
    AnswerResponse,
    IngestResponse,
    QueryRequest,
    RetryAcceptedResponse,
    RetryJobResponse,
    ReviseRequest,
    SearchResult,
)
from .security import require_internal_api_key
from .services import (
    NO_EVIDENCE_RESPONSE,
    evidence_level,
    filter_chunks,
    log_route_decision,
    low_evidence_note,
    retrieve_chunks,
    to_search_result,
)
from .streaming import ndjson_done_only, streaming_generator

logger = setup_logger(__name__)
router = APIRouter()


def _cloud_available() -> bool:
    try:
        from ..config.llm import cloud_llm_is_configured

        return cloud_llm_is_configured(cloud_llm_config)
    except Exception:
        base_url = str(getattr(cloud_llm_config, "base_url", "")).strip().lower()
        api_key = str(getattr(cloud_llm_config, "api_key", "")).strip().lower()
        return bool(base_url and api_key and "example.invalid" not in base_url)


def _no_evidence_response(stream: bool) -> AnswerResponse | StreamingResponse:
    if stream:
        return StreamingResponse(
            ndjson_done_only(NO_EVIDENCE_RESPONSE),
            media_type="application/x-ndjson",
        )
    return AnswerResponse(
        answer=NO_EVIDENCE_RESPONSE,
        citations_used=[],
        citations_retrieved=[],
        citations=[],
    )


@router.post(
    "/ingest",
    response_model=IngestResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def ingest_guideline(
    file: Annotated[UploadFile, File(...)],
    source_name: Annotated[str, Form(...)],
) -> IngestResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are supported.")

    # Enforce a maximum upload size (50 MB) to prevent OOM during ingestion.
    max_ingest_size = 50 * 1024 * 1024
    if file.size is not None and file.size > max_ingest_size:
        raise HTTPException(
            status_code=422,
            detail=(
                f"File too large ({file.size} bytes). "
                f"Maximum is {max_ingest_size} bytes."
            ),
        )

    sources_path = path_config.root / "configs" / "sources.yaml"
    sources = load_sources(sources_path)
    if source_name not in sources:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown source '{source_name}'. Valid: {sorted(sources.keys())}",
        )

    specialty = sources[source_name].get("specialty", "general")
    data_raw_root = getattr(path_config, "data_raw", path_config.root / "data" / "raw")
    if not isinstance(data_raw_root, Path):
        data_raw_root = path_config.root / "data" / "raw"
    dest_dir = data_raw_root / specialty / source_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file.filename

    try:
        with dest_path.open("wb") as output_file:
            shutil.copyfileobj(file.file, output_file)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save file: {exc}",
        ) from exc
    finally:
        file.file.close()

    try:
        report = run_ingestion(
            input_path=dest_path,
            source_name=source_name,
            db_url=db_config.database_url,
        )
    except PipelineError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed at stage {exc.stage}: {exc.message}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("/ingest failed")
        raise HTTPException(status_code=500, detail="Ingestion error") from exc

    return IngestResponse(source_name=source_name, filename=file.filename, **report)


@router.get("/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ready",
        "local_model": local_llm_config.model,
        "cloud_model": cloud_llm_config.model,
        "cloud_available": _cloud_available(),
        "route_threshold": routing_config.llm_route_threshold,
        "force_cloud_llm": routing_config.force_cloud_llm,
        "active_prompt": ACTIVE_PROMPT,
    }


@router.get(
    "/documents/health",
    dependencies=[Depends(require_internal_api_key)],
)
async def documents_health() -> list[dict[str, Any]]:
    """Return per-document stats from the rag_chunks table."""
    with db_manager.raw_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                doc_id,
                metadata->>'source_name' AS source_name,
                COUNT(*)                 AS chunk_count,
                MAX(updated_at)          AS latest_ingestion
            FROM rag_chunks
            GROUP BY doc_id, metadata->>'source_name'
            ORDER BY latest_ingestion DESC
            """
        )
        rows = cur.fetchall()

    return [
        {
            "doc_id": row[0],
            "source_name": row[1],
            "chunk_count": row[2],
            "latest_ingestion": row[3].isoformat() if row[3] else None,
        }
        for row in rows
    ]


@router.post(
    "/query",
    response_model=list[SearchResult],
    dependencies=[Depends(require_internal_api_key)],
)
async def clinical_query(request: QueryRequest) -> list[SearchResult]:
    """Embed the query and return the top-k nearest chunks."""
    try:
        raw_results = retrieve_chunks(
            request.query,
            top_k=request.top_k,
            specialty=request.specialty,
        )
        return [to_search_result(result) for result in raw_results]
    except Exception as exc:
        logger.exception("/query failed")
        raise HTTPException(
            status_code=500,
            detail="RAG inference error",
        ) from exc


@router.post(
    "/answer",
    response_model=AnswerResponse | RetryAcceptedResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def generate_clinical_answer(
    request: AnswerRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    try:
        advanced_retriever = getattr(api_services, "retrieve_chunks_advanced", None)
        if callable(advanced_retriever):
            retrieved = advanced_retriever(
                query=request.query,
                top_k=request.top_k,
                specialty=request.specialty,
                source_name=request.source_name,
                doc_type=request.doc_type,
                score_threshold=request.score_threshold,
                expand_query=request.expand_query,
            )
        else:
            retrieved = retrieve_chunks(
                request.query,
                top_k=request.top_k,
                specialty=request.specialty,
            )
        return await _generate_answer_from_retrieval(
            query=request.query,
            max_tokens=request.max_tokens,
            patient_context=request.patient_context,
            file_context=request.file_context,
            stream=request.stream,
            severity=request.severity,
            specialty=request.specialty,
            retrieved=retrieved,
            route_endpoint="/answer",
            prompt_label=ACTIVE_PROMPT,
            request_type="answer",
            idempotency_key=idempotency_key,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("/answer failed")
        raise HTTPException(
            status_code=500,
            detail="RAG answer error",
        ) from exc


async def _generate_answer_from_retrieval(
    *,
    query: str,
    max_tokens: int,
    patient_context: dict[str, Any] | None,
    file_context: str | None,
    stream: bool,
    severity: str | None,
    specialty: str | None,
    retrieved: list[dict[str, Any]],
    route_endpoint: str,
    prompt_label: str,
    request_type: str,
    idempotency_key: str | None,
) -> Any:
    try:
        filtered = filter_chunks(query, retrieved, specialty=specialty)
        top_chunks = filtered[:MAX_CITATIONS]
        if not top_chunks and not file_context:
            return _no_evidence_response(stream)

        evidence = evidence_level(top_chunks)

        prompt = build_grounded_prompt(
            query,
            top_chunks,
            patient_context=patient_context,
            file_context=file_context,
            evidence_note=low_evidence_note(evidence),
        )
        route = select_generation_provider(
            query=query,
            retrieved_chunks=filtered or retrieved,
            severity=severity,
            prompt_length_chars=len(prompt),
        )
        log_route_decision(
            route_endpoint,
            route.provider,
            route.score,
            route.threshold,
            route.reasons,
            query=query,
            retrieved_count=len(filtered or retrieved),
            top_score=top_chunks[0]["score"] if top_chunks else None,
            evidence=evidence,
            outcome="selected",
        )
        citations_retrieved = [to_search_result(result) for result in top_chunks]

        if stream:
            return StreamingResponse(
                streaming_generator(
                    prompt,
                    max_tokens,
                    citations_retrieved,
                    allow_uncited_answer=bool(file_context),
                    provider=route.provider,
                ),
                media_type="application/x-ndjson",
            )

        try:
            answer_text = await generate_answer(
                prompt,
                max_tokens=max_tokens,
                provider=route.provider,
            )
        except ModelGenerationError as exc:
            if retry_config.retry_enabled and exc.retryable:
                job_id, status = create_retry_job(
                    request_type=request_type,
                    payload={
                        "prompt": prompt,
                        "provider": route.provider,
                        "max_tokens": max_tokens,
                        "prompt_label": prompt_label,
                        "citations_retrieved": [
                            citation.model_dump() for citation in citations_retrieved
                        ],
                    },
                    idempotency_key=idempotency_key,
                )
                return JSONResponse(
                    status_code=202,
                    content=RetryAcceptedResponse(
                        job_id=job_id,
                        status=status,
                    ).model_dump(),
                )
            raise

        renumbered_answer, citations_used = extract_citation_results(
            answer_text,
            citations_retrieved,
            strip_references=True,
        )
        if not citations_used and not file_context:
            return _no_evidence_response(stream)
        return AnswerResponse(
            answer=renumbered_answer,
            citations_used=citations_used,
            citations_retrieved=citations_retrieved,
            citations=citations_used,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("%s failed", route_endpoint)
        raise HTTPException(
            status_code=500,
            detail="RAG answer error",
        ) from exc


@router.post(
    "/revise",
    response_model=AnswerResponse | RetryAcceptedResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def revise_clinical_answer(
    request: ReviseRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    try:
        retrieved = retrieve_chunks(
            request.original_query,
            top_k=request.top_k,
            specialty=request.specialty,
        )
        filtered = filter_chunks(
            request.original_query,
            retrieved,
            specialty=request.specialty,
        )
        top_chunks = filtered[:MAX_CITATIONS]
        if not top_chunks and not request.file_context:
            return _no_evidence_response(request.stream)

        evidence = evidence_level(top_chunks)

        prompt = build_revision_prompt(
            original_question=request.original_query,
            previous_answer=request.previous_answer,
            specialist_feedback=request.feedback,
            chunks=top_chunks,
            patient_context=request.patient_context,
            file_context=request.file_context,
            evidence_note=low_evidence_note(evidence),
        )
        route = select_generation_provider(
            query=request.original_query,
            retrieved_chunks=filtered or retrieved,
            severity=request.severity,
            is_revision=True,
            prompt_length_chars=len(prompt),
        )
        log_route_decision(
            "/revise",
            route.provider,
            route.score,
            route.threshold,
            route.reasons,
            query=request.original_query,
            retrieved_count=len(filtered or retrieved),
            top_score=top_chunks[0]["score"] if top_chunks else None,
            evidence=evidence,
            outcome="selected",
        )
        citations_retrieved = [to_search_result(result) for result in top_chunks]

        if request.stream:
            return StreamingResponse(
                streaming_generator(
                    prompt,
                    request.max_tokens,
                    citations_retrieved,
                    allow_uncited_answer=bool(request.file_context),
                    provider=route.provider,
                ),
                media_type="application/x-ndjson",
            )

        try:
            answer_text = await generate_answer(
                prompt,
                max_tokens=request.max_tokens,
                provider=route.provider,
            )
        except ModelGenerationError as exc:
            if retry_config.retry_enabled and exc.retryable:
                job_id, status = create_retry_job(
                    request_type="revise",
                    payload={
                        "prompt": prompt,
                        "provider": route.provider,
                        "max_tokens": request.max_tokens,
                        "citations_retrieved": [
                            citation.model_dump() for citation in citations_retrieved
                        ],
                    },
                    idempotency_key=idempotency_key,
                )
                return JSONResponse(
                    status_code=202,
                    content=RetryAcceptedResponse(
                        job_id=job_id,
                        status=status,
                    ).model_dump(),
                )
            raise

        renumbered_answer, citations_used = extract_citation_results(
            answer_text,
            citations_retrieved,
            strip_references=False,
        )
        return AnswerResponse(
            answer=renumbered_answer,
            citations_used=citations_used,
            citations_retrieved=citations_retrieved,
            citations=citations_used,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("/revise failed")
        raise HTTPException(
            status_code=500,
            detail="RAG revise error",
        ) from exc


@router.get(
    "/jobs/{job_id}",
    response_model=RetryJobResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def get_retry_job_status(job_id: str) -> RetryJobResponse:
    state = get_retry_job(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")

    return RetryJobResponse(
        job_id=state["job_id"],
        status=RetryJobStatus(state["status"]),
        attempt_count=state["attempt_count"],
        last_error=state.get("last_error") or None,
        created_at=state["created_at"],
        updated_at=state["updated_at"],
        response=state.get("response"),
    )


@router.get(
    "/docs/{doc_id}",
    dependencies=[Depends(require_internal_api_key)],
)
async def fetch_document(doc_id: str) -> FileResponse:
    """Stream the source PDF for a given doc_id (for citation deep links)."""
    source_path = get_source_path_for_doc(doc_id)
    if not source_path:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(source_path)
    data_root = (path_config.root / "data").resolve()

    try:
        resolved = file_path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document file missing") from exc

    if data_root not in resolved.parents and resolved != data_root:
        raise HTTPException(status_code=400, detail="Invalid document path")

    return FileResponse(
        resolved,
        media_type="application/pdf",
        filename=None,
        headers={"Content-Disposition": f"inline; filename={resolved.name}"},
    )
