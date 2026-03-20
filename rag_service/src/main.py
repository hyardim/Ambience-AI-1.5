"""Backward-compatible entrypoint for the full clinical RAG service."""

from .api.app import app
from .api.citations import (
    MAX_CITATIONS,
    extract_citation_results,
    parse_citation_group,
)
from .api.routes import (
    clinical_query,
    fetch_document,
    generate_clinical_answer,
    get_retry_job_status,
    health_check,
    ingest_guideline,
    revise_clinical_answer,
)
from .api.schemas import (
    AnswerRequest,
    AnswerResponse,
    IngestResponse,
    QueryRequest,
    RetryAcceptedResponse,
    RetryJobResponse,
    ReviseRequest,
    SearchResult,
)
from .api.services import (
    filter_chunks,
    log_route_decision,
    retrieve_chunks,
    to_search_result,
)
from .api.streaming import ndjson_done_only, streaming_generator
from .generation.client import ModelGenerationError, generate_answer
from .jobs.retry import RetryJobStatus, create_retry_job, get_retry_job

_extract_citation_results = extract_citation_results
_filter_chunks = filter_chunks
_ndjson_done_only = ndjson_done_only
_parse_citation_group = parse_citation_group
_retrieve_chunks = retrieve_chunks
_streaming_generator = streaming_generator

__all__ = [
    "MAX_CITATIONS",
    "AnswerRequest",
    "AnswerResponse",
    "IngestResponse",
    "ModelGenerationError",
    "QueryRequest",
    "RetryAcceptedResponse",
    "RetryJobResponse",
    "RetryJobStatus",
    "ReviseRequest",
    "SearchResult",
    "app",
    "clinical_query",
    "create_retry_job",
    "extract_citation_results",
    "fetch_document",
    "filter_chunks",
    "generate_answer",
    "generate_clinical_answer",
    "get_retry_job",
    "get_retry_job_status",
    "health_check",
    "ingest_guideline",
    "log_route_decision",
    "ndjson_done_only",
    "parse_citation_group",
    "retrieve_chunks",
    "revise_clinical_answer",
    "streaming_generator",
    "to_search_result",
]
