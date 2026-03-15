import shutil
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from src.api.dependencies import Settings, get_db_url, get_settings
from src.api.schemas import (
    AskRequest,
    AskResponse,
    CitationResponse,
    IngestResponse,
    SourceResponse,
)
from src.config import path_config
from src.ingestion.pipeline import PipelineError, load_sources, run_ingestion
from src.rag.generate import GenerationError, RAGResponse
from src.rag.pipeline import ask
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
    settings: Annotated[Settings, Depends(get_settings)],
    db_url: Annotated[str, Depends(get_db_url)],
) -> AskResponse:
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


@router.post("/ingest", response_model=IngestResponse)
async def ingest_guideline(
    file: Annotated[UploadFile, File(...)],
    source_name: Annotated[str, Form(...)],
    db_url: Annotated[str, Depends(get_db_url)],
) -> IngestResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are supported.")

    sources_path = path_config.root / "configs" / "sources.yaml"
    sources = load_sources(sources_path)
    if source_name not in sources:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown source '{source_name}'. Valid: {sorted(sources.keys())}",
        )

    specialty = sources[source_name].get("specialty", "general")
    dest_dir = path_config.root / "data" / "Medical" / specialty.title() / source_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file.filename

    try:
        with dest_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}") from e
    finally:
        file.file.close()

    try:
        report = run_ingestion(
            input_path=dest_path, source_name=source_name, db_url=db_url
        )
    except PipelineError as e:
        raise HTTPException(
            status_code=500, detail=f"Pipeline failed at stage {e.stage}: {e.message}"
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Ingestion error: {e}") from e

    return IngestResponse(source_name=source_name, filename=file.filename, **report)
