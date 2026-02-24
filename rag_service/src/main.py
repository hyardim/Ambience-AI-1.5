from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.config import OLLAMA_MAX_TOKENS
from src.ingestion.embed import embed_chunks, get_vector_dim, load_embedder
from src.llm.client import generate_answer
from src.llm.prompts import build_grounded_prompt
from src.retrieval.vector_store import init_db, search_similar_chunks

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
    chunk_id: int | None = None
    chunk_index: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_path: str | None = None
    metadata: dict[str, Any] | None = None


class AnswerRequest(QueryRequest):
    max_tokens: int = OLLAMA_MAX_TOKENS


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
        embeddings_result = embed_chunks(model, [{"text": request.query}], batch_size=1)
        query_embedding = embeddings_result[0]["embedding"]

        raw_results = search_similar_chunks(query_embedding, limit=request.top_k)

        return [
            SearchResult(
                text=res["text"],
                source=res.get("metadata", {}).get("filename", "Unknown Source"),
                score=res["score"],
                doc_id=res.get("doc_id"),
                chunk_id=res.get("chunk_id"),
                chunk_index=res.get("chunk_index"),
                page_start=res.get("page_start"),
                page_end=res.get("page_end"),
                section_path=res.get("section_path"),
                metadata=res.get("metadata"),
            )
            for res in raw_results
        ]
    except Exception as e:
        print(f"❌ /query Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"RAG Inference Error: {str(e)}")


@app.post("/answer", response_model=AnswerResponse)
async def generate_clinical_answer(request: AnswerRequest):
    """Retrieve supporting chunks, build a grounded prompt, and call Ollama for an answer."""
    try:
        embeddings_result = embed_chunks(model, [{"text": request.query}], batch_size=1)
        query_embedding = embeddings_result[0]["embedding"]

        retrieved = search_similar_chunks(query_embedding, limit=request.top_k)
        prompt = build_grounded_prompt(request.query, retrieved)

        answer_text = await generate_answer(prompt, max_tokens=request.max_tokens)

        citations = [
            SearchResult(
                text=res["text"],
                source=res.get("metadata", {}).get("filename", "Unknown Source"),
                score=res["score"],
                doc_id=res.get("doc_id"),
                chunk_id=res.get("chunk_id"),
                chunk_index=res.get("chunk_index"),
                page_start=res.get("page_start"),
                page_end=res.get("page_end"),
                section_path=res.get("section_path"),
                metadata=res.get("metadata"),
            )
            for res in retrieved
        ]

        return AnswerResponse(answer=answer_text, citations=citations)
    except Exception as e:
        print(f"❌ /answer Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"RAG Answer Error: {str(e)}")
