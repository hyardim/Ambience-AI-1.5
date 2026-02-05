import httpx
from fastapi import APIRouter, Depends
from core.security import get_current_user
import os 
router = APIRouter()

# This URL comes from our docker-compose.yml environment variables
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag_service:8001")

@router.post("/search")
async def search_clinical_guidelines(query: str, current_user=Depends(get_current_user)):
    """
    Backend acts as the Secure Gateway. It verifies the GP user, 
    then requests evidence from the isolated RAG service.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{RAG_SERVICE_URL}/query",
            json={"query": query, "top_k": 3}
        )
    
    if response.status_code != 200:
        return {"error": "RAG Service Unavailable", "details": response.text}
        
    return response.json()