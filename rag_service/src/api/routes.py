from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_db_url, get_settings
from src.api.schemas import AskRequest, AskResponse, CitationResponse, SourceResponse
from src.rag.pipeline import ask
from src.rag.generate import RAGResponse, GenerationError
from src.retrieval.query import RetrievalError

router = APIRouter()


def _to_response(result: RAGResponse) -> AskResponse:
    return AskResponse(
        answer=result.answer,
        sources=[
            SourceResponse(
                chunk_id=src.chunk_id,
                rerank_score=src.rerank_score,
                citation=CitationResponse(
                    title=src.citation.title,
                    source_name=src.citation.source_name,
                    specialty=src.citation.specialty,
                    section_title=src.citation.section_title,
                    page_start=src.citation.page_start,
                    page_end=src.citation.page_end,
                    source_url=src.citation.source_url,
                ),
            )
            for src in result.sources
        ],
        query=result.query,
        model=result.model,
    )


@router.post("/ask", response_model=AskResponse)
async def ask_route(
    payload: AskRequest,
    settings=Depends(get_settings),
    db_url: str = Depends(get_db_url),
):
    try:
        result = ask(
            query=payload.query,
            db_url=db_url,
            top_k=payload.top_k,
            specialty=payload.specialty,
            source_name=payload.source_name,
            doc_type=payload.doc_type,
            score_threshold=payload.score_threshold,
            expand_query=payload.expand_query,
            settings=settings,
        )
        return _to_response(result)
    except RetrievalError as e:
        raise HTTPException(status_code=502, detail=f"Retrieval failed: {e}") from e
    except GenerationError as e:
        raise HTTPException(status_code=502, detail=f"Generation failed: {e}") from e
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="Internal server error") from e
