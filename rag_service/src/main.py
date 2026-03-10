import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import (
    DATABASE_URL,
    CLOUD_LLM_MODEL,
    FORCE_CLOUD_LLM,
    LLM_MAX_TOKENS,
    LLM_ROUTE_THRESHOLD,
    LOCAL_LLM_MODEL,
    path_config,
)
from .generation.client import generate_answer, warmup_model
from .generation.prompts import (
    ACTIVE_PROMPT,
    build_grounded_prompt,
    build_revision_prompt,
)
from .generation.router import select_generation_provider
from .ingestion.embed import embed_text, get_vector_dim, load_embedder
from .ingestion.pipeline import PipelineError, load_sources, run_ingestion
from .retrieval.vector_store import (
    get_source_path_for_doc,
    init_db,
    search_similar_chunks,
)

app = FastAPI(title="Ambience Med42 RAG Service")

# Load embedding model once and prepare DB schema (pgvector + tables).
print("🏥 Loading Embedding Model...")
model = load_embedder()
VECTOR_DIM = get_vector_dim(model)
print(f"✅ Model Loaded! Embedding dim = {VECTOR_DIM}")


@app.on_event("startup")
def ensure_schema():
    """Create pgvector extension and tables if missing."""
    try:
        init_db(vector_dim=VECTOR_DIM)
        print("✅ Database schema ready (chunks/documents).")
    except Exception as exc:  # pragma: no cover - defensive log only
        print(f"⚠️ Failed to initialize database: {exc}")


@app.on_event("startup")
async def warmup_ollama():
    """Pre-load the selected generation provider on service startup.

    Prevents the first request from hitting a cold provider when applicable.
    """
    if FORCE_CLOUD_LLM:
        print(
            f"☁️ Cloud-only mode enabled. Using cloud model '{CLOUD_LLM_MODEL}'.")
        await warmup_model(provider="cloud")
        return

    print(f"🔥 Warming up local model '{LOCAL_LLM_MODEL}'...")
    await warmup_model()


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
    return {n for m in _CITATION_RE.findall(text) for n in _parse_citation_group(m[1:-1])}


def _rewrite_citations(text: str, renumber_map: dict[int, int]) -> str:
    """Renumber valid citations to sequential display numbers; strip out-of-range ones."""
    def _rewrite(match: re.Match) -> str:
        nums = _parse_citation_group(match.group(0)[1:-1])
        kept = sorted({renumber_map[n] for n in nums if n in renumber_map})
        return f"[{', '.join(str(k) for k in kept)}]" if kept else ""
    return _CITATION_RE.sub(_rewrite, text)


class AnswerResponse(BaseModel):
    answer: str
    citations_used: list[SearchResult]
    citations_retrieved: list[SearchResult]
    citations: list[SearchResult]


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


@app.post("/ingest", response_model=IngestResponse)
async def ingest_guideline(
    file: UploadFile = File(...),
    source_name: str = Form(...),
):
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
        report = run_ingestion(input_path=dest_path, source_name=source_name, db_url=DATABASE_URL)
    except PipelineError as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed at stage {e.stage}: {e.message}") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion error: {e}") from e

    return IngestResponse(source_name=source_name, filename=file.filename, **report)


@app.get("/health")
async def health_check():
    return {
        "status": "ready",
        "local_model": LOCAL_LLM_MODEL,
        "cloud_model": CLOUD_LLM_MODEL,
        "route_threshold": LLM_ROUTE_THRESHOLD,
        "force_cloud_llm": FORCE_CLOUD_LLM,
        "active_prompt": ACTIVE_PROMPT,
    }


@app.post("/query", response_model=list[SearchResult])
async def clinical_query(request: QueryRequest):
    """Embed the query and return the top-k nearest chunks."""
    try:
        embeddings_result = embed_text(model, [request.query], batch_size=1)
        query_embedding = embeddings_result[0]

        raw_results = search_similar_chunks(
            query_embedding, limit=request.top_k)

        return [
            SearchResult(
                text=res["text"],
                source=res.get("metadata", {}).get(
                    "filename", "Unknown Source"),
                score=res["score"],
                doc_id=res.get("doc_id"),
                doc_version=res.get("doc_version"),
                chunk_id=res.get("chunk_id"),
                chunk_index=res.get("chunk_index"),
                content_type=res.get("content_type"),
                page_start=res.get("page_start"),
                page_end=res.get("page_end"),
                section_path=res.get("section_path"),
                metadata=res.get("metadata"),
            )
            for res in raw_results
        ]
    except Exception as e:
        print(f"❌ /query Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"RAG Inference Error: {str(e)}"
        ) from e


@app.post("/answer", response_model=AnswerResponse)
async def generate_clinical_answer(request: AnswerRequest):
    """Retrieve supporting chunks, build a grounded prompt, and call Ollama
    for an answer."""
    try:
        embeddings_result = embed_text(model, [request.query], batch_size=1)
        query_embedding = embeddings_result[0]

        retrieved = search_similar_chunks(query_embedding, limit=request.top_k)

        # Filter out low-relevance hits and chunks missing source_path (broken citations).
        filtered = [
            r
            for r in retrieved
            if r.get("score", 0) >= MIN_RELEVANCE
            and (r.get("metadata") or {}).get("source_path")
            and _has_query_overlap(request.query, r.get("text", ""))
            and not _is_boilerplate(r)
        ]
        top_chunks = filtered[:MAX_CITATIONS]

        if not top_chunks and not request.file_context:
            # Avoid making the model hallucinate when nothing relevant was retrieved
            # and no uploaded document is present.
            return AnswerResponse(
                answer=(
                    "I couldn't find any guideline passage in the indexed sources "
                    "that directly answers this question. Please rephrase or try a different query."
                ),
                citations_used=[],
                citations_retrieved=[],
                citations=[],
            )

        prompt = build_grounded_prompt(request.query, top_chunks, patient_context=request.patient_context, file_context=request.file_context)

        route = select_generation_provider(
            query=request.query,
            retrieved_chunks=filtered or retrieved,
            severity=request.severity,
        )
        print(
            "🧭 /answer routing "
            f"provider={route.provider} score={route.score} "
            f"threshold={route.threshold} reasons={','.join(route.reasons) or 'none'}"
        )
        answer_text = await generate_answer(
            prompt,
            max_tokens=request.max_tokens,
            provider=route.provider,
        )

        used_indices = _extract_citation_indices(answer_text)

        citations_retrieved = [
            SearchResult(
                text=res["text"],
                source=res.get("metadata", {}).get(
                    "filename", "Unknown Source"),
                score=res["score"],
                doc_id=res.get("doc_id"),
                doc_version=res.get("doc_version"),
                chunk_id=res.get("chunk_id"),
                chunk_index=res.get("chunk_index"),
                content_type=res.get("content_type"),
                page_start=res.get("page_start"),
                page_end=res.get("page_end"),
                section_path=res.get("section_path"),
                metadata=res.get("metadata"),
            )
            for res in top_chunks
        ]

        sorted_used = sorted(i for i in used_indices if 1 <= i <= len(citations_retrieved))
        citations_used = [citations_retrieved[i - 1] for i in sorted_used]

        renumber_map = {orig: new for new, orig in enumerate(sorted_used, start=1)}
        renumbered_answer = _rewrite_citations(answer_text, renumber_map)
        # Strip any fabricated plain-text "References:" section the model appends.
        renumbered_answer = re.sub(
            r"\n+\s*References?:.*",
            "",
            renumbered_answer,
            flags=re.DOTALL | re.IGNORECASE,
        ).rstrip()

        labelled_answer = f"[Prompt: {ACTIVE_PROMPT}]\n\n{renumbered_answer}"
        return AnswerResponse(
            answer=labelled_answer,
            citations_used=citations_used,
            citations_retrieved=citations_retrieved,
            citations=citations_used,
        )
    except Exception as e:
        print(f"❌ /answer Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"RAG Answer Error: {str(e)}"
        ) from e


@app.post("/revise", response_model=AnswerResponse)
async def revise_clinical_answer(request: ReviseRequest):
    """Re-generate an AI answer incorporating specialist feedback.

    Retrieval is performed against the *original* patient query so that the
    same (or similar) evidence chunks are used, while the generation prompt
    instructs the model to revise its previous answer according to the
    specialist's feedback.
    """
    try:
        # Retrieve using the original query so chunk relevance stays high.
        embeddings_result = embed_text(
            model, [request.original_query], batch_size=1)
        query_embedding = embeddings_result[0]

        retrieved = search_similar_chunks(query_embedding, limit=request.top_k)

        filtered = [
            r
            for r in retrieved
            if r.get("score", 0) >= MIN_RELEVANCE
            and (r.get("metadata") or {}).get("source_path")
            and _has_query_overlap(request.original_query, r.get("text", ""))
            and not _is_boilerplate(r)
        ]
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
        print(
            "🧭 /revise routing "
            f"provider={route.provider} score={route.score} "
            f"threshold={route.threshold} reasons={','.join(route.reasons) or 'none'}"
        )

        answer_text = await generate_answer(
            prompt,
            max_tokens=request.max_tokens,
            provider=route.provider,
        )

        used_indices = _extract_citation_indices(answer_text)

        citations_retrieved = [
            SearchResult(
                text=res["text"],
                source=res.get("metadata", {}).get(
                    "filename", "Unknown Source"),
                score=res["score"],
                doc_id=res.get("doc_id"),
                doc_version=res.get("doc_version"),
                chunk_id=res.get("chunk_id"),
                chunk_index=res.get("chunk_index"),
                content_type=res.get("content_type"),
                page_start=res.get("page_start"),
                page_end=res.get("page_end"),
                section_path=res.get("section_path"),
                metadata=res.get("metadata"),
            )
            for res in top_chunks
        ]

        sorted_used = sorted(i for i in used_indices if 1 <= i <= len(citations_retrieved))
        citations_used = [citations_retrieved[i - 1] for i in sorted_used]

        renumber_map = {orig: new for new, orig in enumerate(sorted_used, start=1)}
        renumbered_answer = _rewrite_citations(answer_text, renumber_map)

        return AnswerResponse(
            answer=renumbered_answer,
            citations_used=citations_used,
            citations_retrieved=citations_retrieved,
            citations=citations_used,
        )
    except Exception as e:
        print(f"\u274c /revise Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"RAG Revise Error: {str(e)}"
        ) from e


@app.get("/docs/{doc_id}")
async def fetch_document(doc_id: str):
    """Stream the source PDF for a given doc_id (for citation deep links)."""
    source_path = get_source_path_for_doc(doc_id)
    if not source_path:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(source_path)
    data_root = (path_config.root / "data").resolve()

    try:
        resolved = file_path.resolve(strict=True)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document file missing")

    if data_root not in resolved.parents and resolved != data_root:
        raise HTTPException(status_code=400, detail="Invalid document path")

    return FileResponse(
        resolved,
        media_type="application/pdf",
        filename=None,
        headers={"Content-Disposition": f"inline; filename={resolved.name}"},
    )
