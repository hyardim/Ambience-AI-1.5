import json
import re
import shutil
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from .config import (
    CLOUD_LLM_MODEL,
    DATABASE_URL,
    FORCE_CLOUD_LLM,
    LLM_MAX_TOKENS,
    LLM_ROUTE_THRESHOLD,
    LOCAL_LLM_MODEL,
    RETRY_ENABLED,
    path_config,
)
from .generation.client import (
    ModelGenerationError,
    ProviderName,
    generate_answer,
    warmup_model,
)
from .generation.prompts import (
    ACTIVE_PROMPT,
    build_grounded_prompt,
    build_revision_prompt,
)
from .generation.router import select_generation_provider
from .generation.streaming import stream_generate
from .ingestion.embed import embed_text, get_vector_dim, load_embedder
from .ingestion.pipeline import PipelineError, load_sources, run_ingestion
from .retrieval.vector_store import (
    get_source_path_for_doc,
    init_db,
    search_similar_chunks,
)
from .retry_queue import RetryJobStatus, create_retry_job, get_retry_job
from .utils.logger import setup_logger

logger = setup_logger(__name__)


def ensure_schema() -> None:
    """Create pgvector extension and tables if missing."""
    try:
        init_db(vector_dim=get_embedding_dimension())
        logger.info("Database schema ready (chunks/documents).")
    except Exception as exc:  # pragma: no cover - defensive log only
        logger.warning("Failed to initialize database: %s", exc)


async def warmup_ollama() -> None:
    """Pre-load the selected generation provider on service startup.

    Prevents the first request from hitting a cold provider when applicable.
    """
    if FORCE_CLOUD_LLM:
        logger.info("Cloud-only mode enabled. Using cloud model '%s'.", CLOUD_LLM_MODEL)
        await warmup_model(provider="cloud")
        return

    logger.info("Warming up local model '%s'...", LOCAL_LLM_MODEL)
    await warmup_model()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    del app
    get_embedding_dimension()
    ensure_schema()
    await warmup_ollama()
    yield


app = FastAPI(title="Ambience Med42 RAG Service", lifespan=lifespan)


@lru_cache(maxsize=1)
def get_embedding_model() -> Any:
    logger.info("Loading embedding model...")
    model = load_embedder()
    logger.info("Embedding model loaded. dim=%s", get_vector_dim(model))
    return model


@lru_cache(maxsize=1)
def get_embedding_dimension() -> int:
    return get_vector_dim(get_embedding_model())


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    specialty: str | None = None
    severity: str | None = None


class SearchResult(BaseModel):
    text: str
    source: str
    score: float
    doc_id: str | None = None
    doc_version: str | None = None
    chunk_id: str | None = None
    chunk_index: int | None = None
    content_type: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_path: str | None = None
    metadata: dict[str, Any] | None = None


class AnswerRequest(QueryRequest):
    max_tokens: int = LLM_MAX_TOKENS
    patient_context: dict[str, Any] | None = None
    file_context: str | None = None
    stream: bool = False


class ReviseRequest(BaseModel):
    """Request body for the /revise endpoint."""

    original_query: str
    previous_answer: str
    feedback: str
    top_k: int = 5
    max_tokens: int = LLM_MAX_TOKENS
    patient_context: dict[str, Any] | None = None
    file_context: str | None = None
    specialty: str | None = None
    severity: str | None = None
    stream: bool = False


MAX_CITATIONS = 3
MIN_RELEVANCE = 0.25

# Tokens that are too generic to establish relevance on their own.
GENERIC_TOKENS = {
    "guideline",
    "guidelines",
    "recommendation",
    "recommendations",
    "committee",
    "evidence",
    "information",
    "summary",
    "overview",
    "introduction",
    "statement",
    "data",
    "supplementary",
    "material",
    "details",
}


def _has_query_overlap(question: str, chunk_text: str) -> bool:
    """Basic lexical check to ensure the chunk mentions query terms.

    Filters out boilerplate chunks that match semantically but lack shared terms,
    which often leads to irrelevant citations.
    """

    def _tokens(text: str) -> set[str]:
        tokens = {
            t
            for t in re.findall(r"[A-Za-z0-9]+", text.lower())
            if len(t) >= 4 and t not in GENERIC_TOKENS
        }
        return tokens

    q_tokens = _tokens(question)
    c_tokens = _tokens(chunk_text)
    overlap = q_tokens.intersection(c_tokens)
    return bool(q_tokens and c_tokens and overlap)


# Boilerplate phrases that are not helpful for answering clinical questions.
BOILERPLATE_PATTERNS = [
    "data availability",
    "supplementary material",
    "guideline committee",
    "finding more information",
    "evidence reviews",
    "copyright",
    "license",
    "doi",
    "manuscript",
]


def _is_boilerplate(chunk: dict[str, Any]) -> bool:
    text = (chunk.get("text") or "").lower()
    section = ((chunk.get("section_path") or "") or "").lower()
    return any(pat in text or pat in section for pat in BOILERPLATE_PATTERNS)


def _parse_citation_group(raw: str) -> list[int]:
    """Parse a citation group string into a list of ints, handling ranges.

    e.g. '1, 2, 5-7' → [1, 2, 5, 6, 7]
    """
    nums: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                nums.extend(range(int(a), int(b) + 1))
            except ValueError:
                pass
        else:
            try:
                nums.append(int(part))
            except ValueError:
                pass
    return nums


# Matches bracket citations: [1], [1, 2], [1-3], [1, 2, 195-202] etc.
_CITATION_RE = re.compile(r"\[[\d,\s\-]+\]")


def _extract_citation_indices(text: str) -> set[int]:
    """Return all 1-based citation indices found in the text."""
    return {
        n for m in _CITATION_RE.findall(text) for n in _parse_citation_group(m[1:-1])
    }


def _rewrite_citations(text: str, renumber_map: dict[int, int]) -> str:
    """Renumber valid citations and strip out-of-range references."""

    def _rewrite(match: re.Match) -> str:
        nums = _parse_citation_group(match.group(0)[1:-1])
        kept = sorted({renumber_map[n] for n in nums if n in renumber_map})
        return f"[{', '.join(str(k) for k in kept)}]" if kept else ""

    return _CITATION_RE.sub(_rewrite, text)


def _to_search_result(res: dict[str, Any]) -> SearchResult:
    metadata = res.get("metadata") or {}
    return SearchResult(
        text=res["text"],
        source=metadata.get("filename", "Unknown Source"),
        score=res["score"],
        doc_id=res.get("doc_id"),
        doc_version=res.get("doc_version"),
        chunk_id=res.get("chunk_id"),
        chunk_index=res.get("chunk_index"),
        content_type=res.get("content_type"),
        page_start=res.get("page_start"),
        page_end=res.get("page_end"),
        section_path=res.get("section_path"),
        metadata=metadata,
    )


def _embed_query_text(query: str) -> list[float]:
    embeddings_result = embed_text(
        get_embedding_model(),
        [query],
        batch_size=1,
    )
    return embeddings_result[0]


def _retrieve_chunks(
    query: str,
    *,
    top_k: int,
    specialty: str | None,
) -> list[dict[str, Any]]:
    return search_similar_chunks(
        _embed_query_text(query),
        limit=top_k,
        specialty=specialty,
    )


def _filter_chunks(query: str, retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        chunk
        for chunk in retrieved
        if chunk.get("score", 0) >= MIN_RELEVANCE
        and (chunk.get("metadata") or {}).get("source_path")
        and _has_query_overlap(query, chunk.get("text", ""))
        and not _is_boilerplate(chunk)
    ]


def _extract_citation_results(
    answer_text: str,
    citations_retrieved: list[SearchResult],
    *,
    strip_references: bool,
) -> tuple[str, list[SearchResult]]:
    used_indices = _extract_citation_indices(answer_text)
    sorted_used = sorted(i for i in used_indices if 1 <= i <= len(citations_retrieved))
    citations_used = [citations_retrieved[i - 1] for i in sorted_used]
    renumber_map = {orig: new for new, orig in enumerate(sorted_used, start=1)}
    answer = _rewrite_citations(answer_text, renumber_map)
    if strip_references:
        answer = re.sub(
            r"\n+\s*References?:.*",
            "",
            answer,
            flags=re.DOTALL | re.IGNORECASE,
        ).rstrip()
    return answer, citations_used


def _log_route_decision(
    endpoint: str,
    provider: ProviderName,
    route_score: float,
    threshold: float,
    reasons: tuple[str, ...],
) -> None:
    logger.info(
        "%s routing provider=%s score=%s threshold=%s reasons=%s",
        endpoint,
        provider,
        route_score,
        threshold,
        ",".join(reasons) or "none",
    )


class AnswerResponse(BaseModel):
    answer: str
    citations_used: list[SearchResult]
    citations_retrieved: list[SearchResult]
    citations: list[SearchResult]


async def _streaming_generator(
    prompt: str,
    max_tokens: int,
    citations_retrieved: list[SearchResult],
    provider: ProviderName = "local",
) -> AsyncGenerator[str, None]:
    """Yield NDJSON lines: ``chunk`` deltas then a final ``done`` payload."""
    accumulated = ""
    try:
        if provider == "local":
            async for token in stream_generate(prompt, max_tokens=max_tokens):
                accumulated += token
                yield json.dumps({"type": "chunk", "delta": token}) + "\n"
        else:
            accumulated = await generate_answer(
                prompt,
                max_tokens=max_tokens,
                provider=provider,
            )
    except Exception as e:
        yield json.dumps({"type": "error", "error": str(e)}) + "\n"
        return

    renumbered_answer, citations_used = _extract_citation_results(
        accumulated,
        citations_retrieved,
        strip_references=True,
    )
    fallback = citations_used if citations_used else citations_retrieved

    yield (
        json.dumps(
            {
                "type": "done",
                "answer": renumbered_answer,
                "citations_used": [c.model_dump() for c in citations_used],
                "citations_retrieved": [c.model_dump() for c in citations_retrieved],
                "citations": [c.model_dump() for c in fallback],
            }
        )
        + "\n"
    )


async def _ndjson_done_only(answer: str) -> AsyncGenerator[str, None]:
    """Single ``done`` line for cases where no streaming is needed."""
    yield (
        json.dumps(
            {
                "type": "done",
                "answer": answer,
                "citations_used": [],
                "citations_retrieved": [],
                "citations": [],
            }
        )
        + "\n"
    )


class IngestResponse(BaseModel):
    source_name: str
    filename: str
    files_scanned: int
    files_succeeded: int
    files_failed: int
    total_chunks: int
    embeddings_succeeded: int
    embeddings_failed: int
    db: dict


class RetryAcceptedResponse(BaseModel):
    job_id: str
    status: RetryJobStatus


class RetryJobResponse(BaseModel):
    job_id: str
    status: RetryJobStatus
    attempt_count: int
    last_error: str | None = None
    created_at: str
    updated_at: str
    response: dict[str, Any] | None = None


@app.post("/ingest", response_model=IngestResponse)
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
        with dest_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}") from e
    finally:
        file.file.close()

    try:
        report = run_ingestion(
            input_path=dest_path, source_name=source_name, db_url=DATABASE_URL
        )
    except PipelineError as e:
        raise HTTPException(
            status_code=500, detail=f"Pipeline failed at stage {e.stage}: {e.message}"
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion error: {e}") from e

    return IngestResponse(source_name=source_name, filename=file.filename, **report)


@app.get("/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ready",
        "local_model": LOCAL_LLM_MODEL,
        "cloud_model": CLOUD_LLM_MODEL,
        "route_threshold": LLM_ROUTE_THRESHOLD,
        "force_cloud_llm": FORCE_CLOUD_LLM,
        "active_prompt": ACTIVE_PROMPT,
    }


@app.post("/query", response_model=list[SearchResult])
async def clinical_query(request: QueryRequest) -> list[SearchResult]:
    """Embed the query and return the top-k nearest chunks."""
    try:
        raw_results = _retrieve_chunks(
            request.query,
            top_k=request.top_k,
            specialty=request.specialty,
        )
        return [_to_search_result(res) for res in raw_results]
    except Exception as e:
        logger.exception("/query failed")
        raise HTTPException(
            status_code=500, detail=f"RAG Inference Error: {str(e)}"
        ) from e


@app.post("/answer", response_model=AnswerResponse | RetryAcceptedResponse)
async def generate_clinical_answer(
    request: AnswerRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    """Retrieve supporting chunks, build a grounded prompt, and call Ollama
    for an answer."""
    try:
        retrieved = _retrieve_chunks(
            request.query,
            top_k=request.top_k,
            specialty=request.specialty,
        )
        filtered = _filter_chunks(request.query, retrieved)
        top_chunks = filtered[:MAX_CITATIONS]

        no_result = (
            "I couldn't find any guideline passage in the indexed sources "
            "that directly answers this question. Please rephrase or try a "
            "different query."
        )
        if not top_chunks and not request.file_context:
            # Avoid making the model hallucinate when nothing relevant was retrieved
            # and no uploaded document is present.
            if request.stream:
                return StreamingResponse(
                    _ndjson_done_only(no_result),
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
        _log_route_decision(
            "/answer",
            route.provider,
            route.score,
            route.threshold,
            route.reasons,
        )
        citations_retrieved = [_to_search_result(res) for res in top_chunks]

        if request.stream:
            return StreamingResponse(
                _streaming_generator(
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
                        job_id=job_id, status=status
                    ).model_dump(),
                )
            raise

        renumbered_answer, citations_used = _extract_citation_results(
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
    except Exception as e:
        logger.exception("/answer failed")
        raise HTTPException(
            status_code=500, detail=f"RAG Answer Error: {str(e)}"
        ) from e


@app.post("/revise", response_model=AnswerResponse | RetryAcceptedResponse)
async def revise_clinical_answer(
    request: ReviseRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    """Re-generate an AI answer incorporating specialist feedback.

    Retrieval is performed against the *original* patient query so that the
    same (or similar) evidence chunks are used, while the generation prompt
    instructs the model to revise its previous answer according to the
    specialist's feedback.
    """
    try:
        retrieved = _retrieve_chunks(
            request.original_query,
            top_k=request.top_k,
            specialty=request.specialty,
        )
        filtered = _filter_chunks(request.original_query, retrieved)
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
        _log_route_decision(
            "/revise",
            route.provider,
            route.score,
            route.threshold,
            route.reasons,
        )

        citations_retrieved = [_to_search_result(res) for res in top_chunks]

        if request.stream:
            return StreamingResponse(
                _streaming_generator(
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
                        job_id=job_id, status=status
                    ).model_dump(),
                )
            raise

        renumbered_answer, citations_used = _extract_citation_results(
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
    except Exception as e:
        logger.exception("/revise failed")
        raise HTTPException(
            status_code=500, detail=f"RAG Revise Error: {str(e)}"
        ) from e


@app.get("/jobs/{job_id}", response_model=RetryJobResponse)
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


@app.get("/docs/{doc_id}")
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
