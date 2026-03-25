from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
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
from .canonicalization import build_canonical_retrieval_query, parse_allowed_specialties
from .citations import (
    MAX_CITATIONS,
    extract_citation_results,
    is_boilerplate,
)
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

try:
    from ..config import retrieval_config
except ImportError:  # pragma: no cover - compatibility for isolated test stubs
    class _RetrievalConfigFallback:
        retrieval_canonicalization_enabled = False
        retrieval_canonicalization_specialties = "rheumatology"

    retrieval_config = _RetrievalConfigFallback()

ABSOLUTE_MIN_TOP_SCORE = 0.002
HIGH_PRECISION_MIN_TOP_SCORE = 0.02
HIGH_PRECISION_MIN_OVERLAP = 5
HIGH_PRECISION_SOFT_MIN_TOP_SCORE = 0.08
HIGH_PRECISION_MIN_KEY_OVERLAP = 3
HIGH_PRECISION_MIN_OVERLAP_RATIO = 0.12
ANSWER_RETRIEVAL_MIN_TOP_K = 8
MULTIPART_PROMPT_CHUNKS = 5
PROMPT_BACKFILL_SCORE_RATIO = 0.35
HIGH_PRECISION_QUERY_RE = re.compile(
    r"\b(baseline|blood tests?|imaging|investigations?|prior to referral|"
    r"referral pathway|how urgently|urgency)\b",
    re.IGNORECASE,
)
NON_DIRECTIVE_SECTION_HINT_RE = re.compile(
    r"\b(discussion|results|context|background|rationale|headlines|"
    r"why the committee made)\b",
    re.IGNORECASE,
)
DIRECTIVE_SECTION_HINT_RE = re.compile(
    r"\b(recommendation|recommendations|refer|referral|pathway|"
    r"when to refer|urgent|immediate|assessment|investigation)\b",
    re.IGNORECASE,
)
REFERRAL_QUERY_HINT_RE = re.compile(
    r"\b(refer\w*|referr\w*|pathway|urgent|immediate|urgency|"
    r"prior to referral|before referral)\b",
    re.IGNORECASE,
)
REFERRAL_SENTENCE_HINT_RE = re.compile(
    r"\b(refer\w*|referr\w*|pathway|urgent|urgency)\b",
    re.IGNORECASE,
)
INVESTIGATION_QUERY_HINT_RE = re.compile(
    r"\b(investigations?|investigate|baseline|blood tests?|work[- ]?up|"
    r"laboratory|labs?)\b",
    re.IGNORECASE,
)
INVESTIGATION_SENTENCE_HINT_RE = re.compile(
    r"\b(investigations?|blood tests?|fbc|cbc|esr|crp|urinalysis|"
    r"anti-?ccp|rheumatoid factor|rf\b|ana|dsdna|u&es|eGFR|creatinine)\b",
    re.IGNORECASE,
)
IMAGING_QUERY_HINT_RE = re.compile(
    r"\b(imaging|x-?ray|ultrasound|mri|ct|scan)\b",
    re.IGNORECASE,
)
IMAGING_SENTENCE_HINT_RE = re.compile(
    r"\b(x-?ray|ultrasound|mri|ct|scan|imaging)\b",
    re.IGNORECASE,
)
OVERLAP_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "what",
    "when",
    "where",
    "which",
    "should",
    "would",
    "could",
    "patient",
    "patients",
    "male",
    "female",
    "year",
    "years",
    "old",
    "known",
    "new",
    "over",
    "month",
    "months",
}


@dataclass
class _RetrievalPassDecision:
    name: str
    retrieval_query: str
    retrieved: list[dict[str, Any]]
    filtered: list[dict[str, Any]]
    top_chunks: list[dict[str, Any]]
    passes_low_confidence_gate: bool
    has_directive_section_fit: bool
    requested_part_count: int
    covered_part_count: int
    evidence_quality_score: float


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


def _minimum_required_top_score(query: str) -> float:
    if HIGH_PRECISION_QUERY_RE.search(query):
        return HIGH_PRECISION_MIN_TOP_SCORE
    return ABSOLUTE_MIN_TOP_SCORE


def _query_overlap_count(query: str, text: str) -> int:
    def _tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[A-Za-z0-9]+", value.lower())
            if len(token) >= 3 and token not in OVERLAP_STOPWORDS
        }

    return len(_tokens(query).intersection(_tokens(text)))


def _query_overlap_ratio(query: str, text: str) -> float:
    def _tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[A-Za-z0-9]+", value.lower())
            if len(token) >= 3 and token not in OVERLAP_STOPWORDS
        }

    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    overlap = len(query_tokens.intersection(_tokens(text)))
    return overlap / len(query_tokens)


def _should_reject_for_low_confidence(query: str, top_chunk: dict[str, Any]) -> bool:
    top_score = float(top_chunk.get("score", 0.0))
    if top_score < ABSOLUTE_MIN_TOP_SCORE:
        return True
    is_high_precision = bool(HIGH_PRECISION_QUERY_RE.search(query))
    if not is_high_precision:
        return top_score < _minimum_required_top_score(query)

    overlap = _query_overlap_count(query, top_chunk.get("text", ""))
    if top_score < HIGH_PRECISION_MIN_TOP_SCORE:
        return overlap < HIGH_PRECISION_MIN_OVERLAP

    if top_score < HIGH_PRECISION_SOFT_MIN_TOP_SCORE:
        section_path = str(top_chunk.get("section_path") or "")
        if NON_DIRECTIVE_SECTION_HINT_RE.search(section_path):
            return True
        if overlap < HIGH_PRECISION_MIN_KEY_OVERLAP:
            return True
        overlap_ratio = _query_overlap_ratio(query, top_chunk.get("text", ""))
        if overlap_ratio < HIGH_PRECISION_MIN_OVERLAP_RATIO:
            return True

    return False


def _retrieve_for_answer_query(
    request: AnswerRequest,
    *,
    retrieval_query: str,
) -> list[dict[str, Any]]:
    advanced_retriever = getattr(api_services, "retrieve_chunks_advanced", None)
    if callable(advanced_retriever):
        retrieval_top_k = max(request.top_k, ANSWER_RETRIEVAL_MIN_TOP_K)

        def _run_advanced(doc_type: str | None) -> list[dict[str, Any]]:
            return advanced_retriever(
                query=retrieval_query,
                top_k=retrieval_top_k,
                specialty=request.specialty,
                source_name=request.source_name,
                doc_type=doc_type,
                score_threshold=request.score_threshold,
                expand_query=request.expand_query,
            )

        if request.doc_type is not None:
            return _run_advanced(request.doc_type)

        # Guideline-first retrieval: fall back to all document types only
        # when guideline-only retrieval yields no usable evidence.
        guideline_retrieved = _run_advanced("guideline")
        guideline_filtered = filter_chunks(retrieval_query, guideline_retrieved)
        if guideline_filtered:
            return guideline_retrieved
        return _run_advanced(None)

    return retrieve_chunks(
        retrieval_query,
        top_k=request.top_k,
        specialty=request.specialty,
    )


def _has_directive_section_fit(chunks: list[dict[str, Any]]) -> bool:
    for chunk in chunks:
        section_path = str(chunk.get("section_path") or "")
        if not section_path:
            continue
        if NON_DIRECTIVE_SECTION_HINT_RE.search(section_path):
            continue
        if DIRECTIVE_SECTION_HINT_RE.search(section_path):
            return True
    return False


def _evidence_quality_score(chunks: list[dict[str, Any]]) -> float:
    if not chunks:
        return 0.0
    scores = [float(chunk.get("score", 0.0)) for chunk in chunks]
    top_score = scores[0]
    mean_score = sum(scores) / len(scores)
    return (0.7 * top_score) + (0.3 * mean_score)


def _requested_question_parts(query: str) -> list[tuple[str, re.Pattern[str]]]:
    requested_parts: list[tuple[str, re.Pattern[str]]] = []
    if INVESTIGATION_QUERY_HINT_RE.search(query):
        requested_parts.append(("investigations", INVESTIGATION_SENTENCE_HINT_RE))
    if IMAGING_QUERY_HINT_RE.search(query):
        requested_parts.append(("imaging", IMAGING_SENTENCE_HINT_RE))
    if REFERRAL_QUERY_HINT_RE.search(query):
        requested_parts.append(("referral/urgency pathway", REFERRAL_SENTENCE_HINT_RE))
    return requested_parts


def _prompt_chunk_limit(query: str) -> int:
    requested_parts = _requested_question_parts(query)
    if len(requested_parts) >= 2:
        return MULTIPART_PROMPT_CHUNKS
    return MAX_CITATIONS


def _chunk_identity(chunk: dict[str, Any]) -> tuple[Any, ...]:
    metadata = chunk.get("metadata") or {}
    return (
        chunk.get("doc_id"),
        chunk.get("chunk_id"),
        chunk.get("page_start"),
        chunk.get("page_end"),
        metadata.get("source_name"),
    )


def _chunk_has_overlap(query: str, chunk: dict[str, Any]) -> bool:
    text = str(chunk.get("text") or "")
    section_path = str(chunk.get("section_path") or "")
    return (
        _query_overlap_count(query, text) > 0
        or _query_overlap_count(query, section_path) > 0
    )


def _select_prompt_chunks(
    *,
    query: str,
    retrieved: list[dict[str, Any]],
    filtered: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    prompt_chunk_limit = _prompt_chunk_limit(query)
    top_chunks = list(filtered[:prompt_chunk_limit])
    if len(top_chunks) >= prompt_chunk_limit or not retrieved:
        return top_chunks

    top_retrieved_score = max(float(chunk.get("score", 0.0)) for chunk in retrieved)
    backfill_min_score = max(
        ABSOLUTE_MIN_TOP_SCORE,
        top_retrieved_score * PROMPT_BACKFILL_SCORE_RATIO,
    )
    seen = {_chunk_identity(chunk) for chunk in top_chunks}

    backfill_candidates: list[dict[str, Any]] = []
    for chunk in retrieved:
        if len(top_chunks) + len(backfill_candidates) >= prompt_chunk_limit:
            break
        if _chunk_identity(chunk) in seen:
            continue
        if float(chunk.get("score", 0.0)) < backfill_min_score:
            continue
        if is_boilerplate(chunk):
            continue
        if not ((chunk.get("metadata") or {}).get("source_url") or chunk.get("doc_id")):
            continue
        if not _chunk_has_overlap(query, chunk):
            continue
        backfill_candidates.append(chunk)
        seen.add(_chunk_identity(chunk))

    return top_chunks + backfill_candidates


def _covered_question_part_count(
    chunks: list[dict[str, Any]],
    requested_parts: list[tuple[str, re.Pattern[str]]],
) -> int:
    if not requested_parts or not chunks:
        return 0

    covered = 0
    for _, pattern in requested_parts:
        for chunk in chunks:
            haystack = f"{chunk.get('text', '')} {chunk.get('section_path', '')}"
            if pattern.search(haystack):
                covered += 1
                break
    return covered


def _evaluate_retrieval_pass(
    *,
    name: str,
    query: str,
    retrieval_query: str,
    retrieved: list[dict[str, Any]],
) -> _RetrievalPassDecision:
    filtered = filter_chunks(retrieval_query, retrieved)
    top_chunks = _select_prompt_chunks(
        query=query,
        retrieved=retrieved,
        filtered=filtered,
    )
    requested_parts = _requested_question_parts(query)
    covered_part_count = _covered_question_part_count(top_chunks, requested_parts)
    passes_low_confidence_gate = bool(top_chunks) and not (
        _should_reject_for_low_confidence(
            retrieval_query,
            top_chunks[0],
        )
    )
    return _RetrievalPassDecision(
        name=name,
        retrieval_query=retrieval_query,
        retrieved=retrieved,
        filtered=filtered,
        top_chunks=top_chunks,
        passes_low_confidence_gate=passes_low_confidence_gate,
        has_directive_section_fit=(
            passes_low_confidence_gate and _has_directive_section_fit(top_chunks)
        ),
        requested_part_count=len(requested_parts),
        covered_part_count=covered_part_count,
        evidence_quality_score=_evidence_quality_score(top_chunks),
    )


def _pass_rank(decision: _RetrievalPassDecision) -> tuple[int, int, int, float]:
    return (
        int(decision.passes_low_confidence_gate),
        decision.covered_part_count,
        int(decision.has_directive_section_fit),
        decision.evidence_quality_score,
    )


def _select_retrieval_pass(
    primary: _RetrievalPassDecision,
    secondary: _RetrievalPassDecision | None,
) -> _RetrievalPassDecision:
    if secondary is None:
        return primary
    if _pass_rank(secondary) > _pass_rank(primary):
        return secondary
    return primary


def _fallback_reason_from_decision(decision: _RetrievalPassDecision) -> str | None:
    if not decision.top_chunks:
        return "no_relevant_chunks"
    if not decision.passes_low_confidence_gate:
        return "low_confidence_retrieval"
    return None


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
        primary_pass = _evaluate_retrieval_pass(
            name="original",
            query=request.query,
            retrieval_query=request.query,
            retrieved=_retrieve_for_answer_query(
                request,
                retrieval_query=request.query,
            )
        )

        canonicalization_triggered = False
        canonical_pass: _RetrievalPassDecision | None = None
        primary_evidence = evidence_level(primary_pass.top_chunks)

        if retrieval_config.retrieval_canonicalization_enabled and (
            not primary_pass.top_chunks
            or not primary_pass.passes_low_confidence_gate
            or primary_evidence == "weak"
        ):
            allowed_specialties = parse_allowed_specialties(
                retrieval_config.retrieval_canonicalization_specialties
            )
            canonical_query = build_canonical_retrieval_query(
                query=request.query,
                specialty=request.specialty,
                allowed_specialties=allowed_specialties,
            )
            if canonical_query:
                canonicalization_triggered = True
                canonical_pass = _evaluate_retrieval_pass(
                    name="canonical",
                    query=request.query,
                    retrieval_query=canonical_query,
                    retrieved=_retrieve_for_answer_query(
                        request,
                        retrieval_query=canonical_query,
                    ),
                )

        selected_pass = _select_retrieval_pass(primary_pass, canonical_pass)
        return await _generate_answer_from_retrieval(
            query=request.query,
            retrieval_query=selected_pass.retrieval_query,
            max_tokens=request.max_tokens,
            patient_context=request.patient_context,
            file_context=request.file_context,
            stream=request.stream,
            severity=request.severity,
            retrieved=selected_pass.retrieved,
            route_endpoint="/answer",
            prompt_label=ACTIVE_PROMPT,
            request_type="answer",
            idempotency_key=idempotency_key,
            canonicalization_triggered=canonicalization_triggered,
            selected_retrieval_pass=selected_pass.name,
            fallback_reason=_fallback_reason_from_decision(selected_pass),
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
    retrieval_query: str | None = None,
    max_tokens: int,
    patient_context: dict[str, Any] | None,
    file_context: str | None,
    stream: bool,
    severity: str | None,
    retrieved: list[dict[str, Any]],
    route_endpoint: str,
    prompt_label: str,
    request_type: str,
    idempotency_key: str | None,
    canonicalization_triggered: bool | None = None,
    selected_retrieval_pass: str | None = None,
    fallback_reason: str | None = None,
) -> Any:
    try:
        query_for_retrieval = retrieval_query or query
        filtered = filter_chunks(query_for_retrieval, retrieved)
        top_chunks = _select_prompt_chunks(
            query=query,
            retrieved=retrieved,
            filtered=filtered,
        )
        evidence = evidence_level(top_chunks)
        if not top_chunks and not file_context:
            log_route_decision(
                route_endpoint,
                "local",
                0.0,
                routing_config.llm_route_threshold,
                ("no_evidence",),
                query=query,
                retrieved_count=len(filtered or retrieved),
                top_score=None,
                evidence=evidence,
                outcome="fallback",
                canonicalization_triggered=canonicalization_triggered,
                selected_retrieval_pass=selected_retrieval_pass,
                fallback_reason=fallback_reason or "no_relevant_chunks",
            )
            return _no_evidence_response(stream)
        if (
            top_chunks
            and not file_context
            and _should_reject_for_low_confidence(query_for_retrieval, top_chunks[0])
        ):
            log_route_decision(
                route_endpoint,
                "local",
                0.0,
                routing_config.llm_route_threshold,
                ("no_evidence", "low_confidence"),
                query=query,
                retrieved_count=len(filtered or retrieved),
                top_score=top_chunks[0]["score"],
                evidence=evidence,
                outcome="fallback",
                canonicalization_triggered=canonicalization_triggered,
                selected_retrieval_pass=selected_retrieval_pass,
                fallback_reason=fallback_reason or "low_confidence_retrieval",
            )
            return _no_evidence_response(stream)

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
            canonicalization_triggered=canonicalization_triggered,
            selected_retrieval_pass=selected_retrieval_pass,
            fallback_reason=None,
        )
        citations_retrieved = [to_search_result(result) for result in top_chunks]

        if stream:
            return StreamingResponse(
                streaming_generator(
                    prompt,
                    max_tokens,
                    citations_retrieved,
                    provider=route.provider,
                    query=query,
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
            query=query,
        )
        if not renumbered_answer.strip() or not citations_used:
            renumbered_answer = NO_EVIDENCE_RESPONSE
            citations_used = []
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
        filtered = filter_chunks(request.original_query, retrieved)
        top_chunks = filtered[:MAX_CITATIONS]
        if not top_chunks and not request.file_context:
            return _no_evidence_response(request.stream)
        if (
            top_chunks
            and not request.file_context
            and _should_reject_for_low_confidence(
                request.original_query,
                top_chunks[0],
            )
        ):
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
                    provider=route.provider,
                    query=request.original_query,
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
            query=request.original_query,
        )
        if not renumbered_answer.strip():
            renumbered_answer = NO_EVIDENCE_RESPONSE
            citations_used = []
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
