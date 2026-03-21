from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=20)
    specialty: str | None = None
    source_name: str | None = None
    doc_type: str | None = None
    score_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    expand_query: bool = False


class CitationResponse(BaseModel):
    title: str
    source_name: str
    specialty: str
    section_title: str
    page_start: int
    page_end: int
    source_url: str


class SourceResponse(BaseModel):
    chunk_id: str
    rerank_score: float
    citation: CitationResponse


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]
    query: str
    model: str
