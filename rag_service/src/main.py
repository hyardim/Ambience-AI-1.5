import json
import re
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .config import OLLAMA_MAX_TOKENS, OLLAMA_MODEL, path_config
from .generation.client import generate_answer, warmup_model
from .generation.streaming import stream_generate
from .generation.prompts import build_grounded_prompt, build_revision_prompt
from .ingestion.embed import embed_text, get_vector_dim, load_embedder
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
    """Pre-load the Ollama model into memory on service startup.

    Prevents the first real request from hitting a cold model and avoids
    500 errors caused by Ollama silently failing to reload an idle model.
    """
    print(f"🔥 Warming up Ollama model '{OLLAMA_MODEL}'...")
    await warmup_model()


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


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
    max_tokens: int = OLLAMA_MAX_TOKENS
    stream: bool = False


class ReviseRequest(BaseModel):
    """Request body for the /revise endpoint."""
    original_query: str
    previous_answer: str
    feedback: str
    top_k: int = 5
    max_tokens: int = OLLAMA_MAX_TOKENS
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


def _extract_citation_indices(text: str) -> set[int]:
    """Return the set of 1-based indices present as [1], [2], etc."""
    return {int(match) for match in re.findall(r"\[(\d+)\]", text)}


class AnswerResponse(BaseModel):
    answer: str
    citations_used: list[SearchResult]
    citations_retrieved: list[SearchResult]
    citations: list[SearchResult]


async def _streaming_generator(
    prompt: str,
    max_tokens: int,
    citations_retrieved: list[SearchResult],
) -> AsyncGenerator[str, None]:
    """Yield NDJSON lines: ``chunk`` deltas then a final ``done`` payload."""
    accumulated = ""
    try:
        async for token in stream_generate(prompt, max_tokens=max_tokens):
            accumulated += token
            yield json.dumps({"type": "chunk", "delta": token}) + "\n"
    except Exception as e:
        yield json.dumps({"type": "error", "error": str(e)}) + "\n"
        return

    used_indices = _extract_citation_indices(accumulated)
    citations_used = [
        citations_retrieved[i - 1]
        for i in sorted(used_indices)
        if 1 <= i <= len(citations_retrieved)
    ]
    fallback = citations_used if citations_used else citations_retrieved

    yield json.dumps({
        "type": "done",
        "answer": accumulated,
        "citations_used": [c.model_dump() for c in citations_used],
        "citations_retrieved": [c.model_dump() for c in citations_retrieved],
        "citations": [c.model_dump() for c in fallback],
    }) + "\n"


async def _ndjson_done_only(answer: str) -> AsyncGenerator[str, None]:
    """Single ``done`` line for cases where no streaming is needed."""
    yield json.dumps({
        "type": "done",
        "answer": answer,
        "citations_used": [],
        "citations_retrieved": [],
        "citations": [],
    }) + "\n"


@app.get("/health")
async def health_check():
    return {"status": "ready", "model": "Med42-OpenVINO"}


@app.post("/query", response_model=list[SearchResult])
async def clinical_query(request: QueryRequest):
    """Embed the query and return the top-k nearest chunks."""
    try:
        embeddings_result = embed_text(model, [request.query], batch_size=1)
        query_embedding = embeddings_result[0]

        raw_results = search_similar_chunks(query_embedding, limit=request.top_k)

        return [
            SearchResult(
                text=res["text"],
                source=res.get("metadata", {}).get("filename", "Unknown Source"),
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

        if not top_chunks:
            # Avoid making the model hallucinate when nothing relevant was retrieved.
            no_result = (
                "I couldn't find any guideline passage in the indexed sources "
                "that directly answers this question. Please rephrase or try a different query."
            )
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

        prompt = build_grounded_prompt(request.query, top_chunks)

        citations_retrieved = [
            SearchResult(
                text=res["text"],
                source=res.get("metadata", {}).get("filename", "Unknown Source"),
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

        if request.stream:
            return StreamingResponse(
                _streaming_generator(prompt, request.max_tokens, citations_retrieved),
                media_type="application/x-ndjson",
            )

        answer_text = await generate_answer(prompt, max_tokens=request.max_tokens)

        used_indices = _extract_citation_indices(answer_text)

        citations_used = [
            citations_retrieved[i - 1]
            for i in sorted(used_indices)
            if 1 <= i <= len(citations_retrieved)
        ]

        fallback_citations = citations_used if citations_used else citations_retrieved

        return AnswerResponse(
            answer=answer_text,
            citations_used=citations_used,
            citations_retrieved=citations_retrieved,
            citations=fallback_citations,
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
        embeddings_result = embed_text(model, [request.original_query], batch_size=1)
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
        )

        citations_retrieved = [
            SearchResult(
                text=res["text"],
                source=res.get("metadata", {}).get("filename", "Unknown Source"),
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

        if request.stream:
            return StreamingResponse(
                _streaming_generator(prompt, request.max_tokens, citations_retrieved),
                media_type="application/x-ndjson",
            )

        answer_text = await generate_answer(prompt, max_tokens=request.max_tokens)

        used_indices = _extract_citation_indices(answer_text)

        citations_used = [
            citations_retrieved[i - 1]
            for i in sorted(used_indices)
            if 1 <= i <= len(citations_retrieved)
        ]

        fallback_citations = citations_used if citations_used else citations_retrieved

        return AnswerResponse(
            answer=answer_text,
            citations_used=citations_used,
            citations_retrieved=citations_retrieved,
            citations=fallback_citations,
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
