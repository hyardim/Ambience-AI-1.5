from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..config import (
    CLOUD_LLM_MODEL,
    DATABASE_URL,
    FORCE_CLOUD_LLM,
    LLM_ROUTE_THRESHOLD,
    LOCAL_LLM_MODEL,
    RETRY_ENABLED,
    path_config,
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
from ..utils.logger import setup_logger
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
from .services import (
    filter_chunks,
    log_route_decision,
    retrieve_chunks,
    to_search_result,
)
from .streaming import ndjson_done_only, streaming_generator

logger = setup_logger(__name__)
router = APIRouter()


@router.post("/ingest", response_model=IngestResponse)
async def ingest_guideline(
    file: Annotated[UploadFile, File(...)],
    source_name: Annotated[str, Form(...)],
) -> IngestResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are supported.")

    sources_path = path_config.root / "configs" / "sources.yaml"
    sources = load_sources(sources_path)
    if source_name not in sources:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown source '{source_name}'. Valid: {sorted(sources.keys())}",
        )

    specialty = sources[source_name].get("specialty", "general")
    dest_dir = path_config.root / "data" / "Medical" / specialty.title() / source_name
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
            db_url=DATABASE_URL,
        )
    except PipelineError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed at stage {exc.stage}: {exc.message}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingestion error: {exc}") from exc

    return IngestResponse(source_name=source_name, filename=file.filename, **report)


@router.get("/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ready",
        "local_model": LOCAL_LLM_MODEL,
        "cloud_model": CLOUD_LLM_MODEL,
        "route_threshold": LLM_ROUTE_THRESHOLD,
        "force_cloud_llm": FORCE_CLOUD_LLM,
        "active_prompt": ACTIVE_PROMPT,
    }


@router.post("/query", response_model=list[SearchResult])
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
            detail=f"RAG Inference Error: {str(exc)}",
        ) from exc


@router.post("/answer", response_model=AnswerResponse | RetryAcceptedResponse)
async def generate_clinical_answer(
    request: AnswerRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    try:
        retrieved = retrieve_chunks(
            request.query,
            top_k=request.top_k,
            specialty=request.specialty,
        )
        filtered = filter_chunks(request.query, retrieved)
        top_chunks = filtered[:MAX_CITATIONS]

        no_result = (
            "I couldn't find any guideline passage in the indexed sources "
            "that directly answers this question. Please rephrase or try a "
            "different query."
        )
        if not top_chunks and not request.file_context:
            if request.stream:
                return StreamingResponse(
                    ndjson_done_only(no_result),
                    media_type="application/x-ndjson",
                )
            return AnswerResponse(
                answer=no_result,
                citations_used=[],
                citations_retrieved=[],
                citations=[],
            )

        prompt = build_grounded_prompt(
            request.query,
            top_chunks,
            patient_context=request.patient_context,
            file_context=request.file_context,
        )
        route = select_generation_provider(
            query=request.query,
            retrieved_chunks=filtered or retrieved,
            severity=request.severity,
        )
        log_route_decision(
            "/answer",
            route.provider,
            route.score,
            route.threshold,
            route.reasons,
        )
        citations_retrieved = [to_search_result(result) for result in top_chunks]

        if request.stream:
            return StreamingResponse(
                streaming_generator(
                    prompt,
                    request.max_tokens,
                    citations_retrieved,
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
            if RETRY_ENABLED and exc.retryable:
                job_id, status = create_retry_job(
                    request_type="answer",
                    payload={
                        "prompt": prompt,
                        "provider": route.provider,
                        "max_tokens": request.max_tokens,
                        "prompt_label": ACTIVE_PROMPT,
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
        return AnswerResponse(
            answer=renumbered_answer,
            citations_used=citations_used,
            citations_retrieved=citations_retrieved,
            citations=citations_used,
        )
    except Exception as exc:
        logger.exception("/answer failed")
        raise HTTPException(
            status_code=500,
            detail=f"RAG Answer Error: {str(exc)}",
        ) from exc


@router.post("/revise", response_model=AnswerResponse | RetryAcceptedResponse)
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
        filtered = filter_chunks(request.original_query, retrieved)
        top_chunks = filtered[:MAX_CITATIONS]

        prompt = build_revision_prompt(
            original_question=request.original_query,
            previous_answer=request.previous_answer,
            specialist_feedback=request.feedback,
            chunks=top_chunks,
            patient_context=request.patient_context,
            file_context=request.file_context,
        )
        route = select_generation_provider(
            query=request.original_query,
            retrieved_chunks=filtered or retrieved,
            severity=request.severity,
            is_revision=True,
        )
        log_route_decision(
            "/revise",
            route.provider,
            route.score,
            route.threshold,
            route.reasons,
        )
        citations_retrieved = [to_search_result(result) for result in top_chunks]

        if request.stream:
            return StreamingResponse(
                streaming_generator(
                    prompt,
                    request.max_tokens,
                    citations_retrieved,
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
            if RETRY_ENABLED and exc.retryable:
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
    except Exception as exc:
        logger.exception("/revise failed")
        raise HTTPException(
            status_code=500,
            detail=f"RAG Revise Error: {str(exc)}",
        ) from exc


@router.get("/jobs/{job_id}", response_model=RetryJobResponse)
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


@router.get("/docs/{doc_id}")
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
