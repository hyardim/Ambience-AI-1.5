from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from src.core.config import settings
from src.core.security import get_current_user
from src.services.rag_client import build_rag_headers

router = APIRouter()


@router.post("/search")
async def search_clinical_guidelines(
    query: str,
    specialty: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    """Proxy evidence retrieval through the authenticated backend."""
    async with httpx.AsyncClient(
        timeout=settings.RAG_REQUEST_TIMEOUT_SECONDS
    ) as client:
        try:
            rag_headers = build_rag_headers()
            request_kwargs: dict[str, Any] = {}
            if rag_headers:
                request_kwargs["headers"] = rag_headers
            response = await client.post(
                f"{settings.RAG_SERVICE_URL}/query",
                json={
                    "query": query,
                    "top_k": 3,
                    **({"specialty": specialty} if specialty else {}),
                },
                **request_kwargs,
            )
        except httpx.ConnectError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="RAG service is unavailable.",
            ) from exc
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="RAG request timed out.",
            ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail="RAG service request failed.",
        )

    return response.json()


@router.get("/documents/{doc_id}")
async def fetch_rag_document(
    doc_id: str,
    current_user=Depends(get_current_user),
):
    """Proxy a stored RAG source document through the authenticated backend."""
    async with httpx.AsyncClient(
        timeout=settings.RAG_REQUEST_TIMEOUT_SECONDS
    ) as client:
        try:
            response = await client.get(
                f"{settings.RAG_SERVICE_URL}/docs/{doc_id}",
                headers=build_rag_headers(),
            )
        except httpx.ConnectError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="RAG service is unavailable.",
            ) from exc
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="RAG request timed out.",
            ) from exc

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Document not found.")
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail="RAG service request failed.",
        )

    headers = {}
    content_type = response.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type
    content_disposition = response.headers.get("content-disposition")
    if content_disposition:
        headers["Content-Disposition"] = content_disposition

    return Response(
        content=response.content,
        media_type=content_type or "application/pdf",
        headers=headers,
    )
