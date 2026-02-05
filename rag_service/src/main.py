from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os

# Import your friend's logic (Ensure these are in the same src folder)
from .embed import load_embedder, embed_chunks
from .db import search_similar_chunks

app = FastAPI(title="Ambience Med42 RAG Service")

# 1. Load the model once at startup to keep the service fast
# OpenVINO optimization happens inside your friend's load_embedder()
model = load_embedder()

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

class SearchResult(BaseModel):
    text: str
    source: str
    score: float

@app.get("/health")
async def health_check():
    return {"status": "ready", "model": "Med42-OpenVINO"}

@app.post("/query", response_model=List[SearchResult])
async def clinical_query(request: QueryRequest):
    """
    1. Embeds the GP's question using OpenVINO.
    2. Searches the Guideline Database using pgvector.
    3. Returns the most relevant clinical evidence.
    """
    try:
        # Step 1: Vectorize the question
        # We wrap the query in a list because embed_chunks expects a batch
        query_embedding = embed_chunks(model, [{"text": request.query}])[0]["embedding"]

        # Step 2: Search the database (The logic we fixed in app/db/utils.py)
        # In a multi-service setup, this RAG service calls its own db.py
        raw_results = search_similar_chunks(query_embedding, limit=request.top_k)

        # Step 3: Format for the Backend API
        return [
            SearchResult(
                text=res["text"],
                source=res.get("filename", "Unknown Source"),
                score=res["score"]
            ) for res in raw_results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG Inference Error: {str(e)}")