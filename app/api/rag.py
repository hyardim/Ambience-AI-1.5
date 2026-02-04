from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------
# IMPORT FIX: We use 'app.' because your folder is named 'app'
# ---------------------------------------------------------
from app.db.utils import search_similar_chunks 

router = APIRouter()

# Load the AI Model (Matches your database's 768 dimensions)
print("Loading Embedding Model...")
model = SentenceTransformer('all-mpnet-base-v2')
print("Model Loaded!")

# Define the request shape
class QueryRequest(BaseModel):
    query: str
    k: Optional[int] = 3

@router.post("/search")
async def search_documents(request: QueryRequest):
    try:
        # 1. Convert text -> vector
        query_vector = model.encode(request.query).tolist()

        # 2. Search database
        results = search_similar_chunks(query_vector, limit=request.k)

        return {"count": len(results), "results": results}

    except Exception as e:
        print(f"Search Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))