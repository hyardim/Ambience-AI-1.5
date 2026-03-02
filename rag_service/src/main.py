from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import OLLAMA_MAX_TOKENS, path_config
from .generation.client import generate_answer
from .generation.prompts import build_grounded_prompt
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


MAX_CITATIONS = 3


class AnswerResponse(BaseModel):
    answer: str
    citations: list[SearchResult]


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
        prompt = build_grounded_prompt(request.query, retrieved[:MAX_CITATIONS])

        answer_text = await generate_answer(prompt, max_tokens=request.max_tokens)

        citations = [
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
            for res in retrieved[:MAX_CITATIONS]
        ]

        return AnswerResponse(answer=answer_text, citations=citations)
    except Exception as e:
        print(f"❌ /answer Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"RAG Answer Error: {str(e)}"
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
