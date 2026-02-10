from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import os

# ✅ FIX 1: Import embed_chunks explicitly
from src.ingestion.embed import load_embedder, embed_chunks

# ✅ FIX 2: Import search logic from the new 'retrieval' folder
# (We renamed db.py to vector_store.py in the migration)
from src.retrieval.vector_store import search_similar_chunks

app = FastAPI(title="Ambience Med42 RAG Service")

# Load model at startup
# (Ensure your embed.py has a 'load_embedder' function!)
print("🏥 Loading Embedding Model...")
model = load_embedder()
print("✅ Model Loaded!")

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
    1. Embeds the GP's question.
    2. Searches the Guideline Database.
    3. Returns relevant evidence.
    """
    try:
        # Step 1: Vectorize the question
        # We wrap the query in a list because embed_chunks expects a batch
        embeddings_result = embed_chunks(model, [{"text": request.query}])
        query_embedding = embeddings_result[0]["embedding"]

        # Step 2: Search the database
        raw_results = search_similar_chunks(query_embedding, limit=request.top_k)

        # Step 3: Format for the Backend API
        return [
            SearchResult(
                text=res["text"],
                # Use .get() to avoid crashing if filename is missing
                source=res.get("metadata", {}).get("filename", "Unknown Source"),
                score=res["score"]
            ) for res in raw_results
        ]
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"RAG Inference Error: {str(e)}")