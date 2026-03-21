from fastapi import APIRouter, Depends, HTTPException

from ..generation.prompts import ACTIVE_PROMPT
from ..retrieval.query import RetrievalError
from . import services as api_services
from .ask_schemas import (
    AskRequest,
    AskResponse,
    CitationResponse,
    SourceResponse,
)
from .routes import _generate_answer_from_retrieval
from .schemas import AnswerResponse
from .security import require_internal_api_key

router = APIRouter()


def _to_response(result: AnswerResponse, query: str) -> AskResponse:
    return AskResponse(
        answer=result.answer,
        sources=[
            SourceResponse(
                chunk_id=src.chunk_id or "",
                rerank_score=src.score,
                citation=CitationResponse(
                    title=(src.metadata or {}).get("title")
                    or src.source
                    or "Unknown Source",
                    source_name=(src.metadata or {}).get("source_name")
                    or src.source
                    or "Unknown Source",
                    specialty=(src.metadata or {}).get("specialty") or "general",
                    section_title=src.section_path or "Unknown section",
                    page_start=src.page_start or 0,
                    page_end=src.page_end or src.page_start or 0,
                    source_url=(src.metadata or {}).get("source_url")
                    or (f"/docs/{src.doc_id}" if src.doc_id else ""),
                ),
            )
            for src in result.citations_retrieved
        ],
        query=query,
        model=ACTIVE_PROMPT,
    )


@router.post(
    "/ask",
    response_model=AskResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def ask_route(
    payload: AskRequest,
) -> AskResponse:
    try:
        advanced_retriever = getattr(api_services, "retrieve_chunks_advanced", None)
        if callable(advanced_retriever):
            retrieved = advanced_retriever(
                query=payload.query,
                top_k=payload.top_k,
                specialty=payload.specialty,
                source_name=payload.source_name,
                doc_type=payload.doc_type,
                score_threshold=payload.score_threshold,
                expand_query=payload.expand_query,
            )
        else:
            # Backward-compatible fallback for minimal service stubs.
            retrieved = api_services.retrieve_chunks(
                payload.query,
                top_k=payload.top_k,
                specialty=payload.specialty,
            )
        response = await _generate_answer_from_retrieval(
            query=payload.query,
            max_tokens=1024,
            patient_context=None,
            file_context=None,
            stream=False,
            severity=None,
            retrieved=retrieved,
            route_endpoint="/ask",
            prompt_label=ACTIVE_PROMPT,
            request_type="answer",
            idempotency_key=None,
        )
        if not isinstance(response, AnswerResponse):
            raise HTTPException(status_code=502, detail="Unexpected response type")
        return _to_response(response, payload.query)
    except RetrievalError as e:
        raise HTTPException(status_code=502, detail=f"Retrieval failed: {e}") from e
    except HTTPException as e:
        if e.status_code == 500 and e.detail == "RAG answer error":
            raise HTTPException(
                status_code=502,
                detail=f"Generation failed: {e.detail}",
            ) from e
        raise
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Internal server error") from e
