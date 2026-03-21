from __future__ import annotations

from src.api import citations
from src.retrieval import citation as citation_mod
from src.retrieval import (
    filters,
    fusion,
    keyword_search,
    query,
    rerank,
    retrieve,
    vector_search,
)
from src.retrieval.filters import FilterConfig
from src.retrieval.fusion import FusedResult
from src.retrieval.keyword_search import KeywordSearchResult
from src.retrieval.rerank import RankedResult
from src.retrieval.vector_search import VectorSearchResult


def _metadata(**overrides):
    base = {
        "title": "NICE Guideline",
        "source_name": "NICE",
        "specialty": "neurology",
        "doc_type": "guideline",
        "source_url": "https://example.org",
        "content_type": "text",
        "section_title": "Treatment",
        "section_path": ["Treatment"],
        "page_start": 3,
        "page_end": 4,
        "publish_date": "2024-01-01",
        "last_updated_date": "2024-02-01",
    }
    base.update(overrides)
    return base


def test_query_processing_to_vector_search(monkeypatch):
    class _FakeVec:
        def tolist(self):
            return [0.1] * query.EMBEDDING_DIMENSIONS

    class _FakeModel:
        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            return [_FakeVec()]

    monkeypatch.setattr(query, "_load_model", lambda: _FakeModel())

    processed = query.process_query("RRMS escalation pathway", expand=True)
    assert processed.expanded
    assert len(processed.embedding) == query.EMBEDDING_DIMENSIONS

    monkeypatch.setattr(
        vector_search.psycopg2,
        "connect",
        lambda _: type("Conn", (), {"close": lambda self: None})(),
    )
    monkeypatch.setattr(vector_search, "register_vector", lambda conn: None)
    monkeypatch.setattr(
        vector_search.psycopg2.extras, "register_default_jsonb", lambda conn: None
    )
    monkeypatch.setattr(
        vector_search,
        "_run_query",
        lambda conn, query_embedding, top_k, specialty, source_name, doc_type: [
            VectorSearchResult(
                chunk_id="c1",
                doc_id="d1",
                text="result",
                score=0.9,
                metadata=_metadata(),
            )
        ],
    )

    results = vector_search.vector_search(
        processed.embedding, db_url="postgres://test", top_k=5
    )
    assert len(results) == 1
    assert results[0].score == 0.9


def test_vector_and_keyword_search_parallel(monkeypatch):
    monkeypatch.setattr(
        vector_search,
        "vector_search",
        lambda **kwargs: [
            VectorSearchResult(
                chunk_id="v1",
                doc_id="d1",
                text="vector result",
                score=0.88,
                metadata=_metadata(),
            )
        ],
    )
    monkeypatch.setattr(
        keyword_search,
        "keyword_search",
        lambda **kwargs: [
            KeywordSearchResult(
                chunk_id="k1",
                doc_id="d2",
                text="keyword result",
                rank=0.33,
                metadata=_metadata(title="Local Protocol"),
            )
        ],
    )

    vr = vector_search.vector_search(
        query_embedding=[0.1], db_url="postgres://x", top_k=3
    )
    kr = keyword_search.keyword_search(query="rrms", db_url="postgres://x", top_k=3)
    assert vr
    assert kr
    assert vr[0].chunk_id != kr[0].chunk_id


def test_fusion_combines_vector_and_keyword():
    vector_results = [
        VectorSearchResult(
            chunk_id="c1", doc_id="d1", text="A", score=0.91, metadata=_metadata()
        ),
        VectorSearchResult(
            chunk_id="c2", doc_id="d1", text="B", score=0.8, metadata=_metadata()
        ),
    ]
    keyword_results = [
        KeywordSearchResult(
            chunk_id="c2", doc_id="d1", text="B", rank=0.6, metadata=_metadata()
        ),
        KeywordSearchResult(
            chunk_id="c3",
            doc_id="d2",
            text="C",
            rank=0.5,
            metadata=_metadata(title="Protocol"),
        ),
    ]

    fused = fusion.reciprocal_rank_fusion(vector_results, keyword_results, top_k=5)
    assert fused
    assert len({r.chunk_id for r in fused}) == len(fused)
    assert any(r.chunk_id == "c2" for r in fused)


def test_filters_remove_low_relevance_and_boilerplate():
    fused = [
        FusedResult(
            chunk_id="c1",
            doc_id="d1",
            text="boilerplate copyright text",
            rrf_score=0.5,
            vector_score=0.1,
            keyword_rank=0.1,
            metadata=_metadata(section_title="Data availability"),
        ),
        FusedResult(
            chunk_id="c2",
            doc_id="d1",
            text="clinically relevant treatment guidance",
            rrf_score=0.6,
            vector_score=0.85,
            keyword_rank=0.2,
            metadata=_metadata(),
        ),
    ]

    filtered = filters.apply_filters(fused, FilterConfig(score_threshold=0.25))
    filtered = [
        r
        for r in filtered
        if not citations.is_boilerplate(
            {
                "text": r.text,
                "section_path": " ".join(r.metadata.get("section_path", [])),
            }
        )
    ]
    assert len(filtered) == 1
    assert filtered[0].chunk_id == "c2"


def test_rerank_reorders_by_cross_encoder(monkeypatch):
    fused = [
        FusedResult(
            chunk_id="c1",
            doc_id="d1",
            text="first",
            rrf_score=0.4,
            vector_score=0.7,
            keyword_rank=0.5,
            metadata=_metadata(),
        ),
        FusedResult(
            chunk_id="c2",
            doc_id="d1",
            text="second",
            rrf_score=0.5,
            vector_score=0.8,
            keyword_rank=0.4,
            metadata=_metadata(),
        ),
    ]

    class _FakeCrossEncoder:
        def __init__(self, name):
            self.name = name

        def predict(self, pairs):
            return [0.1, 2.0]

    monkeypatch.setattr(rerank, "_CrossEncoder", _FakeCrossEncoder)
    monkeypatch.setattr(rerank, "_model", None)
    monkeypatch.setattr(rerank, "_model_name_loaded", None)

    ranked = rerank.rerank("question", fused, top_k=2)
    assert ranked[0].chunk_id == "c2"
    assert ranked[0].rerank_score > ranked[1].rerank_score


def test_dedup_removes_near_duplicates():
    ranked = [
        RankedResult(
            chunk_id="c1",
            doc_id="d1",
            text="same text content",
            rerank_score=0.9,
            rrf_score=0.6,
            vector_score=0.8,
            keyword_rank=0.2,
            metadata=_metadata(),
        ),
        RankedResult(
            chunk_id="c2",
            doc_id="d1",
            text="same text content",
            rerank_score=0.7,
            rrf_score=0.5,
            vector_score=0.7,
            keyword_rank=0.3,
            metadata=_metadata(),
        ),
    ]
    deduped = rerank.deduplicate(ranked, similarity_threshold=0.85)
    assert len(deduped) == 1
    assert deduped[0].chunk_id == "c1"


def test_citation_assembly_from_results():
    ranked = [
        RankedResult(
            chunk_id="c1",
            doc_id="d1",
            text="A",
            rerank_score=0.9,
            rrf_score=0.7,
            vector_score=0.9,
            keyword_rank=0.2,
            metadata=_metadata(),
        ),
        RankedResult(
            chunk_id="c2",
            doc_id="d1",
            text="B",
            rerank_score=0.8,
            rrf_score=0.6,
            vector_score=0.8,
            keyword_rank=0.3,
            metadata=_metadata(title="Protocol"),
        ),
    ]
    cited = citation_mod.assemble_citations(ranked)
    answer = "Use option one [1]."
    renumbered, used = citations.extract_citation_results(
        answer,
        [
            type(
                "SR",
                (),
                c.citation.model_dump()
                | {
                    "score": 0.9,
                    "snippet": c.text,
                    "source": c.citation.title,
                    "source_name": c.citation.source_name,
                    "source_url": c.citation.source_url,
                    "doc_id": c.citation.doc_id,
                    "chunk_id": c.chunk_id,
                    "section": c.citation.section_title,
                    "page_start": c.citation.page_start,
                    "page_end": c.citation.page_end,
                },
            )
            for c in cited
        ],
        strip_references=True,
    )
    assert "[1]" in renumbered
    assert len(used) == 1


def test_full_retrieval_query_to_citations(monkeypatch):
    monkeypatch.setattr(
        retrieve,
        "process_query",
        lambda query, expand=False: type(
            "PQ",
            (),
            {
                "expanded": query,
                "embedding": [0.1],
                "model_dump": lambda self, exclude=None: {
                    "original": query,
                    "expanded": query,
                },
            },
        )(),
    )
    monkeypatch.setattr(
        retrieve,
        "vector_search",
        lambda **kwargs: [
            VectorSearchResult(
                chunk_id="c1",
                doc_id="d1",
                text="rrms relapse treatment",
                score=0.9,
                metadata=_metadata(),
            )
        ],
    )
    monkeypatch.setattr(
        retrieve,
        "keyword_search",
        lambda **kwargs: [
            KeywordSearchResult(
                chunk_id="c2",
                doc_id="d2",
                text="relapse dosing guidance",
                rank=0.7,
                metadata=_metadata(title="Local protocol"),
            )
        ],
    )

    class _FakeCrossEncoder:
        def __init__(self, name):
            self.name = name

        def predict(self, pairs):
            return [2.0, 1.0]

    monkeypatch.setattr(rerank, "_CrossEncoder", _FakeCrossEncoder)
    monkeypatch.setattr(rerank, "_model", None)
    monkeypatch.setattr(rerank, "_model_name_loaded", None)

    cited = retrieve.retrieve(
        query="RRMS relapse management",
        db_url="postgres://test",
        top_k=2,
        specialty="neurology",
    )

    assert cited
    assert citations.has_query_overlap("RRMS relapse management", cited[0].text)
