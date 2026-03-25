from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api import routes
from src.api.schemas import QueryRequest, SearchResult
from src.main import app


@pytest.mark.anyio
async def test_health_check_reports_cloud_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "_cloud_available", lambda: False)

    result = await routes.health_check()

    assert result["status"] == "ready"
    assert result["cloud_available"] is False


def test_prompt_chunk_limit_is_dynamic_for_multipart_queries() -> None:
    assert (
        routes._prompt_chunk_limit(
            "What baseline blood tests and imaging should be completed prior to referral?"
        )
        == routes.MULTIPART_PROMPT_CHUNKS
    )
    assert (
        routes._prompt_chunk_limit("Is routine referral needed for Bell's palsy?")
        == routes.MAX_CITATIONS
    )


def test_select_prompt_chunks_backfills_when_filtered_is_sparse() -> None:
    query = (
        "Older patient with scalp tenderness and jaw claudication. "
        "What urgent action is recommended?"
    )
    primary = {
        "text": "Consider blood tests and follow local pathways for temporal arteritis.",
        "score": 0.55,
        "section_path": "Referral pathway",
        "metadata": {"source_url": "https://example.com/guide-a.pdf"},
        "doc_id": "doc-a",
        "chunk_id": "chunk-a",
    }
    backfill = {
        "text": "Urgent referral for suspected giant cell arteritis should be arranged.",
        "score": 0.3,
        "section_path": "Urgent referral",
        "metadata": {"source_url": "https://example.com/guide-b.pdf"},
        "doc_id": "doc-b",
        "chunk_id": "chunk-b",
    }
    irrelevant = {
        "text": "Quality statement audience section with service specification details.",
        "score": 0.32,
        "section_path": "Audience and scope",
        "metadata": {"source_url": "https://example.com/guide-c.pdf"},
        "doc_id": "doc-c",
        "chunk_id": "chunk-c",
    }

    selected = routes._select_prompt_chunks(
        query=query,
        retrieved=[primary, backfill, irrelevant],
        filtered=[primary],
    )

    assert selected[0] == primary
    assert backfill in selected
    assert irrelevant not in selected


def test_select_prompt_chunks_does_not_backfill_below_score_threshold() -> None:
    query = "What urgent referral pathway should be used?"
    primary = {
        "text": "Refer immediately via urgent pathway.",
        "score": 0.5,
        "section_path": "Referral pathway",
        "metadata": {"source_url": "https://example.com/guide-a.pdf"},
        "doc_id": "doc-a",
        "chunk_id": "chunk-a",
    }
    low_score = {
        "text": "Urgent pathway mention in low-confidence supporting material.",
        "score": 0.1,
        "section_path": "Context",
        "metadata": {"source_url": "https://example.com/guide-b.pdf"},
        "doc_id": "doc-b",
        "chunk_id": "chunk-b",
    }

    selected = routes._select_prompt_chunks(
        query=query,
        retrieved=[primary, low_score],
        filtered=[primary],
    )

    assert selected == [primary]


def test_select_prompt_chunks_seeds_missing_multipart_part_coverage() -> None:
    query = (
        "What baseline blood tests and imaging should be completed prior to referral?"
    )
    referral = {
        "text": "Refer urgently if persistent synovitis affects multiple joints.",
        "score": 0.95,
        "section_path": "Recommendations > Referral pathway",
        "metadata": {"source_url": "https://example.com/referral.pdf"},
        "doc_id": "doc-r",
        "chunk_id": "chunk-r",
    }
    investigations = {
        "text": "Offer rheumatoid factor and consider anti-CCP if RF negative.",
        "score": 0.9,
        "section_path": "Recommendations > Investigations",
        "metadata": {"source_url": "https://example.com/investigations.pdf"},
        "doc_id": "doc-i",
        "chunk_id": "chunk-i",
    }
    context = {
        "text": "General context on inflammatory arthritis prevalence.",
        "score": 0.82,
        "section_path": "Discussion",
        "metadata": {"source_url": "https://example.com/context.pdf"},
        "doc_id": "doc-c",
        "chunk_id": "chunk-c",
    }
    imaging = {
        "text": "X-ray the hands and feet before referral where persistent synovitis is suspected.",
        "score": 0.5,
        "section_path": "Recommendations > Imaging",
        "metadata": {"source_url": "https://example.com/imaging.pdf"},
        "doc_id": "doc-x",
        "chunk_id": "chunk-x",
    }

    filtered = [
        referral,
        investigations,
        context,
        {**referral, "chunk_id": "chunk-r2"},
        {**investigations, "chunk_id": "chunk-i2"},
    ]
    retrieved = [*filtered, imaging]

    selected = routes._select_prompt_chunks(
        query=query,
        retrieved=retrieved,
        filtered=filtered,
    )

    assert imaging in selected
    assert context not in selected


def test_select_prompt_chunks_skips_low_quality_part_seed_candidates() -> None:
    query = (
        "What baseline blood tests and imaging should be completed prior to referral?"
    )
    referral = {
        "text": "Refer urgently if persistent synovitis affects multiple joints.",
        "score": 0.95,
        "section_path": "Recommendations > Referral pathway",
        "metadata": {"source_url": "https://example.com/referral.pdf"},
        "doc_id": "doc-r",
        "chunk_id": "chunk-r",
    }
    investigations = {
        "text": "Offer rheumatoid factor and consider anti-CCP if RF negative.",
        "score": 0.9,
        "section_path": "Recommendations > Investigations",
        "metadata": {"source_url": "https://example.com/investigations.pdf"},
        "doc_id": "doc-i",
        "chunk_id": "chunk-i",
    }
    context = {
        "text": "General context on inflammatory arthritis prevalence.",
        "score": 0.82,
        "section_path": "Discussion",
        "metadata": {"source_url": "https://example.com/context.pdf"},
        "doc_id": "doc-c",
        "chunk_id": "chunk-c",
    }
    low_quality_imaging = {
        "text": "X-ray mention with weak confidence only.",
        "score": 0.1,
        "section_path": "Discussion",
        "metadata": {"source_url": "https://example.com/imaging-weak.pdf"},
        "doc_id": "doc-x",
        "chunk_id": "chunk-x",
    }

    filtered = [referral, investigations, context, {**referral, "chunk_id": "chunk-r2"}]
    retrieved = [*filtered, low_quality_imaging]

    selected = routes._select_prompt_chunks(
        query=query,
        retrieved=retrieved,
        filtered=filtered,
    )

    assert low_quality_imaging not in selected


def test_prepare_prompt_chunks_narrows_mixed_numbered_recommendation_chunk() -> None:
    query = (
        "65-year-old with rapidly progressive gait disturbance and urinary "
        "incontinence over 3 months. CT head shows ventriculomegaly. Should "
        "normal pressure hydrocephalus be suspected and how urgently should this "
        "be referred?"
    )
    chunk = {
        "text": (
            "1.4.2 Refer immediately for assessment for possible vascular event "
            "using local stroke pathways if rapidly progressive unsteady gait is "
            "present within days to weeks.\n"
            "1.4.4 Refer adults with difficulty initiating and coordinating "
            "walking (gait apraxia) to neurology or an elderly care clinic to "
            "exclude normal pressure hydrocephalus."
        ),
        "score": 0.9,
        "section_path": "Recommendations > Rapidly progressive unsteady gait",
        "metadata": {"source_url": "https://example.com/guide.pdf"},
        "doc_id": "doc-1",
        "chunk_id": "chunk-1",
    }

    prepared = routes._prepare_prompt_chunks(query, [chunk])

    assert len(prepared) == 1
    assert "exclude normal pressure hydrocephalus" in prepared[0]["text"]
    assert "possible vascular event" not in prepared[0]["text"]


def test_has_balanced_differential_support_requires_both_sides() -> None:
    query = (
        "How can migraine aura be distinguished from TIA in primary care?"
    )
    both_supported = [
        {
            "text": (
                "Migraine aura may present with transient visual symptoms, while "
                "TIA should be considered for sudden focal neurological deficit."
            ),
            "section_path": "Recommendations",
        }
    ]
    one_sided = [
        {
            "text": "Migraine aura can present with transient visual disturbance.",
            "section_path": "Recommendations",
        }
    ]

    assert routes._has_balanced_differential_support(query, both_supported) is True
    assert routes._has_balanced_differential_support(query, one_sided) is False


@pytest.mark.anyio
async def test_clinical_query_wraps_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> list[dict[str, object]]:
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "retrieve_chunks", boom)

    with pytest.raises(HTTPException, match="RAG inference error"):
        await routes.clinical_query(QueryRequest(query="q"))


@pytest.mark.anyio
async def test_clinical_query_returns_search_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "retrieve_chunks",
        lambda query, top_k, specialty: [
            {
                "text": "chunk",
                "score": 0.9,
                "metadata": {"filename": "guide.pdf"},
                "doc_id": "doc-1",
            }
        ],
    )

    result = await routes.clinical_query(QueryRequest(query="q"))

    assert result == [
        SearchResult(
            text="chunk",
            source="guide.pdf",
            score=0.9,
            doc_id="doc-1",
            metadata={"filename": "guide.pdf"},
        )
    ]


@pytest.mark.anyio
async def test_fetch_document_rejects_paths_outside_data_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outside_file = tmp_path / "outside.pdf"
    outside_file.write_bytes(b"pdf")
    monkeypatch.setattr(
        routes,
        "get_source_path_for_doc",
        lambda doc_id: str(outside_file),
    )

    with pytest.raises(HTTPException, match="Invalid document path"):
        await routes.fetch_document("doc-1")


@pytest.mark.anyio
async def test_fetch_document_returns_file_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    doc = tmp_path / "data" / "doc.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"pdf")
    monkeypatch.setattr(routes, "path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(routes, "get_source_path_for_doc", lambda doc_id: str(doc))

    response = await routes.fetch_document("doc-1")

    assert response.path == doc.resolve()


def test_ingest_guideline_wraps_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("RAG_ENV", "test")
    client = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setattr(routes, "path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(
        routes,
        "load_sources",
        lambda path: {"NICE": {"specialty": "neurology"}},
    )

    def boom(**kwargs: object) -> dict[str, object]:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(routes, "run_ingestion", boom)

    response = client.post(
        "/ingest",
        files={"file": ("guide.pdf", b"%PDF", "application/pdf")},
        data={"source_name": "NICE"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Ingestion error"


@pytest.mark.anyio
async def test_ingest_guideline_rejects_oversized_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(routes, "path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(
        routes,
        "load_sources",
        lambda path: {"NICE": {"specialty": "neurology"}},
    )

    oversized_file = SimpleNamespace(
        filename="guide.pdf",
        size=(50 * 1024 * 1024) + 1,
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.ingest_guideline(oversized_file, "NICE")

    assert exc_info.value.status_code == 422
    assert "File too large" in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_generate_clinical_answer_preserves_http_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [
            {
                "text": "supported chunk",
                "score": 0.9,
                "metadata": {"source_url": "https://example.com/guideline"},
                "doc_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(
        routes,
        "build_grounded_prompt",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            HTTPException(status_code=418, detail="teapot")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.generate_clinical_answer(
            routes.AnswerRequest(query="q", stream=True)
        )

    assert exc_info.value.status_code == 418
    assert exc_info.value.detail == "teapot"


@pytest.mark.anyio
async def test_revise_clinical_answer_preserves_http_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "retrieve_chunks",
        lambda query, top_k, specialty: [
            {
                "text": "supported chunk",
                "score": 0.9,
                "metadata": {"source_url": "https://example.com/guideline"},
                "doc_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(
        routes,
        "build_revision_prompt",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            HTTPException(status_code=422, detail="bad stream")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.revise_clinical_answer(
            routes.ReviseRequest(
                original_query="q",
                previous_answer="a",
                feedback="f",
                stream=True,
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "bad stream"


@pytest.mark.anyio
async def test_revise_clinical_answer_returns_no_evidence_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "retrieve_chunks", lambda query, top_k, specialty: [])
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: [])

    response = await routes.revise_clinical_answer(
        routes.ReviseRequest(
            original_query="q",
            previous_answer="a",
            feedback="f",
            stream=False,
        )
    )

    assert response.answer == routes.NO_EVIDENCE_RESPONSE


@pytest.mark.anyio
async def test_generate_clinical_answer_generic_exception_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lines 180-182: generic Exception handler in /answer endpoint."""

    def boom_retrieve(*args: object, **kwargs: object) -> list[dict[str, object]]:
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: boom_retrieve(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.generate_clinical_answer(
            routes.AnswerRequest(query="q", stream=False)
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "RAG answer error"


@pytest.mark.anyio
async def test_generate_clinical_answer_forwards_advanced_retrieval_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        captured.update(kwargs)
        return [
            {
                "text": "chunk",
                "score": 0.9,
                "metadata": {"title": "Guide"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args, **kwargs):
        return "A"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (
            answer,
            citations[:1],
        ),
    )

    await routes.generate_clinical_answer(
        routes.AnswerRequest(
            query="q",
            specialty="neurology",
            source_name="NICE",
            doc_type="guideline",
            score_threshold=0.42,
            expand_query=True,
            stream=False,
        )
    )

    assert captured["query"] == "q"
    assert captured["specialty"] == "neurology"
    assert captured["source_name"] == "NICE"
    assert captured["doc_type"] == "guideline"
    assert captured["score_threshold"] == 0.42
    assert captured["expand_query"] is True
    assert captured["top_k"] == max(8, routes._answer_retrieval_min_top_k())


@pytest.mark.anyio
async def test_generate_clinical_answer_falls_back_when_advanced_retriever_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    monkeypatch.delattr(routes.api_services, "retrieve_chunks_advanced", raising=False)

    def fake_basic(query: str, *, top_k: int, specialty: str | None):
        called.update({"query": query, "top_k": top_k, "specialty": specialty})
        return [
            {
                "text": "chunk",
                "score": 0.9,
                "metadata": {"title": "Guide"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes, "retrieve_chunks", fake_basic)
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args, **kwargs):
        return "A"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (
            answer,
            citations[:1],
        ),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query="q", top_k=3, specialty="neurology")
    )

    assert response.answer == "A"
    assert called == {"query": "q", "top_k": 3, "specialty": "neurology"}


@pytest.mark.anyio
async def test_generate_clinical_answer_keeps_larger_requested_top_k_for_advanced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        captured.update(kwargs)
        return [
            {
                "text": "chunk",
                "score": 0.9,
                "metadata": {"title": "Guide", "source_url": "https://example.com"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args, **kwargs):
        return "A"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (
            answer,
            citations[:1],
        ),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query="q", top_k=12, stream=False)
    )

    assert response.answer == "A"
    assert captured["top_k"] == 12


@pytest.mark.anyio
async def test_generate_clinical_answer_prefers_guideline_retrieval_when_usable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_type_calls: list[str | None] = []

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        doc_type = kwargs.get("doc_type")
        doc_type_calls.append(doc_type if isinstance(doc_type, str) else None)
        if doc_type == "guideline":
            return [
                {
                    "text": (
                        "Refer urgently via nephrology pathway for lupus nephritis."
                    ),
                    "score": 0.9,
                    "section_path": "Recommendations > Referral pathway",
                    "metadata": {
                        "title": "Guideline",
                        "source_url": "https://example.com/guideline",
                    },
                    "doc_id": "doc-g",
                }
            ]
        return [
            {
                "text": "Fallback chunk",
                "score": 0.9,
                "metadata": {"title": "Paper", "source_url": "https://example.com/paper"},
                "doc_id": "doc-p",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (answer, citations),
    )

    async def fake_generate_answer(*args, **kwargs):
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(
            query="SLE with proteinuria referral pathway",
            stream=False,
        )
    )

    assert response.answer == "Answer [1]"
    assert doc_type_calls == ["guideline"]


@pytest.mark.anyio
async def test_generate_clinical_answer_falls_back_to_all_docs_when_guideline_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_type_calls: list[str | None] = []

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        doc_type = kwargs.get("doc_type")
        doc_type_calls.append(doc_type if isinstance(doc_type, str) else None)
        if doc_type == "guideline":
            return []
        return [
            {
                "text": "Refer urgently via nephrology pathway.",
                "score": 0.9,
                "metadata": {"title": "Paper", "source_url": "https://example.com/paper"},
                "doc_id": "doc-p",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (answer, citations),
    )

    async def fake_generate_answer(*args, **kwargs):
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(
            query="SLE with proteinuria referral pathway",
            stream=False,
        )
    )

    assert response.answer == "Answer [1]"
    assert doc_type_calls == ["guideline", None]


@pytest.mark.anyio
async def test_generate_clinical_answer_no_evidence_for_low_score_high_precision_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [
            {
                "text": "weakly related chunk",
                "score": 0.01,
                "metadata": {"source_url": "https://example.com/doc"},
                "doc_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(
            query=(
                "What baseline blood tests and imaging should be completed prior "
                "to referral?"
            ),
            stream=False,
        )
    )

    assert response.answer == routes.NO_EVIDENCE_RESPONSE


@pytest.mark.anyio
async def test_generate_clinical_answer_allows_weak_differential_with_balanced_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = "How can migraine aura be distinguished from TIA in primary care?"

    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [
            {
                "text": (
                    "Migraine aura may present with transient visual symptoms, while "
                    "TIA should be considered for sudden focal neurological deficit."
                ),
                "score": 0.57,
                "section_path": "Recommendations > Differential diagnosis",
                "metadata": {"source_url": "https://example.com/guide"},
                "doc_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args, **kwargs):
        return "Differentiate migraine aura from TIA using symptom profile [1]."

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (answer, citations),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query=query, specialty="neurology", stream=False)
    )

    assert response.answer != routes.NO_EVIDENCE_RESPONSE


@pytest.mark.anyio
async def test_generate_clinical_answer_rejects_weak_differential_without_balanced_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = "How can migraine aura be distinguished from TIA in primary care?"

    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [
            {
                "text": "Migraine aura can present with transient visual disturbance.",
                "score": 0.57,
                "section_path": "Recommendations",
                "metadata": {"source_url": "https://example.com/guide"},
                "doc_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query=query, specialty="neurology", stream=False)
    )

    assert response.answer == routes.NO_EVIDENCE_RESPONSE


@pytest.mark.anyio
async def test_generate_clinical_answer_uses_canonical_pass_when_primary_is_weak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = (
        "35-year-old with intermittent joint swelling in knees and wrists over "
        "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
        "tests and imaging should be completed prior to referral?"
    )
    canonical_query = "canonical persistent synovitis retrieval query"
    prompt_chunks: dict[str, object] = {}
    telemetry_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.setattr(
        routes,
        "retrieval_config",
        SimpleNamespace(
            retrieval_canonicalization_enabled=True,
            retrieval_canonicalization_specialties="rheumatology",
        ),
    )
    monkeypatch.setattr(
        routes,
        "build_canonical_retrieval_query",
        lambda **kwargs: canonical_query,
    )

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        if kwargs["query"] == canonical_query:
            return [
                {
                    "text": "Refer urgently for suspected persistent synovitis.",
                    "score": 0.9,
                    "section_path": "Recommendations > Referral pathway",
                    "metadata": {"source_url": "https://example.com/guideline"},
                    "doc_id": "doc-2",
                }
            ]
        return [
            {
                "text": "Off-target contextual chunk.",
                "score": 0.001,
                "section_path": "Discussion",
                "metadata": {"source_url": "https://example.com/paper"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    def fake_build_grounded_prompt(*args: object, **kwargs: object) -> str:
        prompt_chunks["chunks"] = args[1]
        return "p"

    monkeypatch.setattr(routes, "build_grounded_prompt", fake_build_grounded_prompt)
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )

    def fake_log(*args: object, **kwargs: object) -> None:
        telemetry_calls.append((args, kwargs))

    monkeypatch.setattr(routes, "log_route_decision", fake_log)

    async def fake_generate_answer(*args, **kwargs):
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (answer, citations),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query=query, specialty="rheumatology", stream=False)
    )

    assert response.answer == "Answer [1]"
    assert prompt_chunks["chunks"][0]["text"] == (
        "Refer urgently for suspected persistent synovitis."
    )
    assert telemetry_calls
    _, selected_call = telemetry_calls[-1]
    assert selected_call["canonicalization_triggered"] is True
    assert selected_call["selected_retrieval_pass"] == "canonical"


@pytest.mark.anyio
async def test_generate_clinical_answer_both_weak_passes_return_no_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = (
        "35-year-old with intermittent joint swelling in knees and wrists over "
        "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
        "tests and imaging should be completed prior to referral?"
    )
    canonical_query = "canonical persistent synovitis retrieval query"
    telemetry_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.setattr(
        routes,
        "retrieval_config",
        SimpleNamespace(
            retrieval_canonicalization_enabled=True,
            retrieval_canonicalization_specialties="rheumatology",
        ),
    )
    monkeypatch.setattr(
        routes,
        "build_canonical_retrieval_query",
        lambda **kwargs: canonical_query,
    )

    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [
            {
                "text": "Weak context only.",
                "score": 0.001,
                "section_path": "Discussion",
                "metadata": {"source_url": "https://example.com/paper"},
                "doc_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)

    def fake_log(*args: object, **kwargs: object) -> None:
        telemetry_calls.append((args, kwargs))

    monkeypatch.setattr(routes, "log_route_decision", fake_log)

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query=query, specialty="rheumatology", stream=False)
    )

    assert response.answer == routes.NO_EVIDENCE_RESPONSE
    assert telemetry_calls
    _, fallback_call = telemetry_calls[-1]
    assert fallback_call["outcome"] == "fallback"
    assert fallback_call["fallback_reason"] == "low_confidence_retrieval"


@pytest.mark.anyio
async def test_canonical_pass_selected_for_weak_primary_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = (
        "35-year-old with intermittent joint swelling in knees and wrists over "
        "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
        "tests and imaging should be completed prior to referral?"
    )
    canonical_query = "canonical persistent synovitis retrieval query"
    telemetry_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.setattr(
        routes,
        "retrieval_config",
        SimpleNamespace(
            retrieval_canonicalization_enabled=True,
            retrieval_canonicalization_specialties="rheumatology",
        ),
    )
    monkeypatch.setattr(
        routes,
        "build_canonical_retrieval_query",
        lambda **kwargs: canonical_query,
    )

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        if kwargs["query"] == canonical_query:
            return [
                {
                    "text": "Refer urgently for suspected persistent synovitis.",
                    "score": 0.9,
                    "section_path": "Recommendations > Referral pathway",
                    "metadata": {"source_url": "https://example.com/guideline"},
                    "doc_id": "doc-2",
                }
            ]
        return [
            {
                "text": "Contextual rheumatology discussion paragraph.",
                "score": 0.56,
                "section_path": "Discussion",
                "metadata": {"source_url": "https://example.com/paper"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )

    def fake_log(*args: object, **kwargs: object) -> None:
        telemetry_calls.append((args, kwargs))

    monkeypatch.setattr(routes, "log_route_decision", fake_log)

    async def fake_generate_answer(*args, **kwargs):
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (answer, citations),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query=query, specialty="rheumatology", stream=False)
    )

    assert response.answer == "Answer [1]"
    assert telemetry_calls
    _, selected_call = telemetry_calls[-1]
    assert selected_call["canonicalization_triggered"] is True
    assert selected_call["selected_retrieval_pass"] == "canonical"


@pytest.mark.anyio
async def test_generate_clinical_answer_tries_canonical_for_referral_query_without_directive_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = (
        "65-year-old with rapidly progressive gait disturbance and urinary "
        "incontinence over 3 months. CT head shows ventriculomegaly. Should "
        "normal pressure hydrocephalus be suspected and how urgently should this "
        "be referred?"
    )
    canonical_query = "canonical nph retrieval query"
    telemetry_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.setattr(
        routes,
        "retrieval_config",
        SimpleNamespace(
            retrieval_canonicalization_enabled=True,
            retrieval_canonicalization_specialties="neurology",
        ),
    )
    monkeypatch.setattr(
        routes,
        "build_canonical_retrieval_query",
        lambda **kwargs: canonical_query,
    )

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        if kwargs["query"] == canonical_query:
            return [
                {
                    "text": (
                        "Refer adults with gait apraxia to neurology to exclude "
                        "normal pressure hydrocephalus."
                    ),
                    "score": 0.6,
                    "section_path": "Recommendations > Referral pathway",
                    "metadata": {"source_url": "https://example.com/guideline"},
                    "doc_id": "doc-2",
                }
            ]
        return [
            {
                "text": "General discussion of sudden-onset unsteady gait.",
                "score": 0.9,
                "section_path": "Discussion",
                "metadata": {"source_url": "https://example.com/paper"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )

    def fake_log(*args: object, **kwargs: object) -> None:
        telemetry_calls.append((args, kwargs))

    monkeypatch.setattr(routes, "log_route_decision", fake_log)

    async def fake_generate_answer(*args, **kwargs):
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (answer, citations),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query=query, specialty="neurology", stream=False)
    )

    assert response.answer == "Answer [1]"
    assert telemetry_calls
    _, selected_call = telemetry_calls[-1]
    assert selected_call["canonicalization_triggered"] is True
    assert selected_call["selected_retrieval_pass"] == "canonical"


@pytest.mark.anyio
async def test_generate_clinical_answer_falls_back_when_no_valid_citations_extracted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [
            {
                "text": "Refer urgently for suspected persistent synovitis.",
                "score": 0.9,
                "section_path": "Recommendations > Referral pathway",
                "metadata": {"source_url": "https://example.com/guideline"},
                "doc_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args, **kwargs):
        return "Honest scope note with no grounded citations."

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (answer, []),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query="q", stream=False)
    )

    assert response.answer == routes.NO_EVIDENCE_RESPONSE
    assert response.citations_used == []


def test_should_reject_for_low_confidence_high_precision_nondirective_section() -> None:
    query = (
        "What baseline blood tests and imaging should be completed prior to referral?"
    )
    top_chunk = {
        "text": "ESR and CRP can be raised in SLE and infection contexts.",
        "score": 0.069,
        "section_path": "D > Rationale",
    }

    assert routes._should_reject_for_low_confidence(query, top_chunk) is True


def test_low_confidence_gate_keeps_high_precision_directive_section() -> None:
    query = (
        "What baseline blood tests and imaging should be completed prior to referral?"
    )
    top_chunk = {
        "text": (
            "Baseline blood tests include ESR and CRP. Complete imaging before "
            "referral using the referral pathway recommendations."
        ),
        "score": 0.069,
        "section_path": "Recommendations > Referral pathway",
    }

    assert routes._should_reject_for_low_confidence(query, top_chunk) is False


def test_passes_low_confidence_gate_allows_partial_part_coverage() -> None:
    query = (
        "What baseline blood tests and imaging should be completed prior to referral?"
    )
    top_chunks = [
        {
            "text": "Baseline blood tests include ESR and CRP.",
            "score": 0.03,
            "section_path": "Discussion",
        }
    ]

    assert (
        routes._passes_low_confidence_gate(
            query=query,
            retrieval_query=query,
            top_chunks=top_chunks,
        )
        is True
    )


def test_treatment_initiation_query_rejects_low_score_weak_overlap() -> None:
    query = "Type 1 diabetes with recurrent nocturnal hypoglycaemia: should insulin pump therapy be started now?"
    top_chunk = {
        "text": (
            "Maintain blood glucose concentration and provide insulin therapy "
            "for acute stroke."
        ),
        "score": 0.08,
        "section_path": "Blood sugar control",
    }

    assert routes._should_reject_for_low_confidence(query, top_chunk) is True


def test_treatment_initiation_query_keeps_high_score_chunk() -> None:
    query = (
        "Should polymyalgia rheumatica be started on steroids in primary care?"
    )
    top_chunk = {
        "text": (
            "Start prednisolone treatment for polymyalgia rheumatica after "
            "excluding key alternative diagnoses."
        ),
        "score": 0.82,
        "section_path": "Guideline recommendations",
    }

    assert routes._should_reject_for_low_confidence(query, top_chunk) is False


@pytest.mark.anyio
async def test_generate_clinical_answer_repairs_missing_citations_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [
            {
                "text": "Refer urgently for suspected persistent synovitis.",
                "score": 0.9,
                "section_path": "Recommendations > Referral pathway",
                "metadata": {"source_url": "https://example.com/guideline"},
                "doc_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "build_revision_prompt",
        lambda *args, **kwargs: "repair-prompt",
    )
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    call_count = {"count": 0}

    async def fake_generate_answer(prompt: str, **kwargs: object) -> str:
        call_count["count"] += 1
        if prompt == "repair-prompt":
            return "Fixed answer [1]"
        return "Draft answer without citations"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    def fake_extract(
        answer: str,
        citations: list[object],
        strip_references: bool,
        query: str | None = None,
    ) -> tuple[str, list[object]]:
        if "Fixed answer" in answer:
            return answer, citations[:1]
        return answer, []

    monkeypatch.setattr(routes, "extract_citation_results", fake_extract)

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query="q", stream=False)
    )

    assert response.answer == "Fixed answer [1]"
    assert response.citations_used
    assert call_count["count"] == 2


@pytest.mark.anyio
async def test_documents_health_returns_per_document_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover the /documents/health endpoint (lines 149-168)."""
    from datetime import datetime, timezone

    ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    class FakeCursor:
        def execute(self, sql: str) -> None:
            pass

        def fetchall(self) -> list[tuple[str, str, int, datetime]]:
            return [
                ("doc-1", "NICE", 5, ts),
                ("doc-2", "WHO", 3, None),
            ]

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *args: object) -> None:
            pass

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def close(self) -> None:
            pass

    monkeypatch.setattr(routes.db_manager, "get_raw_connection", FakeConnection)

    result = await routes.documents_health()

    assert result == [
        {
            "doc_id": "doc-1",
            "source_name": "NICE",
            "chunk_count": 5,
            "latest_ingestion": ts.isoformat(),
        },
        {
            "doc_id": "doc-2",
            "source_name": "WHO",
            "chunk_count": 3,
            "latest_ingestion": None,
        },
    ]


@pytest.mark.anyio
async def test_documents_health_closes_connection_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure the connection is closed even when the query raises."""
    closed: list[bool] = []

    class FailCursor:
        def execute(self, sql: str) -> None:
            raise RuntimeError("db error")

        def __enter__(self) -> FailCursor:
            return self

        def __exit__(self, *args: object) -> None:
            pass

    class FakeConnection:
        def cursor(self) -> FailCursor:
            return FailCursor()

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(routes.db_manager, "get_raw_connection", FakeConnection)

    with pytest.raises(RuntimeError, match="db error"):
        await routes.documents_health()

    assert closed == [True]
