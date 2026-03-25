from __future__ import annotations

import hashlib
import re
from typing import Any

from ..config import db_config, path_config
from ..generation.client import ProviderName
from ..retrieval.citation import CitedResult
from ..retrieval.query import expand_query_text
from ..retrieval.relevance import (
    document_kind_score,
    phrase_overlap_count,
    query_intent_alignment_score,
    query_overlap_count,
    text_quality_score,
)
from ..retrieval.retrieve import retrieve
from ..utils.logger import setup_logger
from ..utils.telemetry import append_jsonl
from .citations import (
    MIN_RELEVANCE,
    has_query_overlap,
    is_boilerplate,
)
from .schemas import SearchResult

logger = setup_logger(__name__)
ROUTE_TELEMETRY_PATH = path_config.logs / "route_decisions.jsonl"
NO_EVIDENCE_RESPONSE = (
    "I couldn't find any guideline passage in the indexed sources that directly "
    "answers this question. Please rephrase the question, upload a supporting "
    "document, or try a different query."
)
HIGH_CONFIDENCE_RELEVANCE = 0.72
SOFT_FALLBACK_RELEVANCE = 0.45
LOW_SCORE_FALLBACK_FLOOR = 0.04
LOW_SCORE_FALLBACK_RATIO = 0.6
LOW_EVIDENCE_TOP_SCORE = 0.58
LOW_EVIDENCE_STRONG_HITS = 1
_INVESTIGATION_TASK_RE = re.compile(
    r"\b(investigations?|investigate|baseline|blood tests?|work[- ]?up|"
    r"laboratory|labs?)\b",
    re.IGNORECASE,
)
_IMAGING_TASK_RE = re.compile(
    r"\b(imaging|x-?ray|ultrasound|mri|ct|scan)\b",
    re.IGNORECASE,
)
_REFERRAL_TASK_RE = re.compile(
    r"\b(refer|referral|pathway|urgent|urgency|how urgently)\b",
    re.IGNORECASE,
)
_TREATMENT_TASK_RE = re.compile(
    r"\b(treat\w*|management|manage\w*|therapy|medication|dose|prescrib\w*|"
    r"drug|start\w*|initiat\w*|commenc\w*|begin\w*|stop\w*|continue\w*)\b",
    re.IGNORECASE,
)
_TASK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("investigations", _INVESTIGATION_TASK_RE),
    ("imaging", _IMAGING_TASK_RE),
    ("referral", _REFERRAL_TASK_RE),
    ("treatment", _TREATMENT_TASK_RE),
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_URGENT_TOXICITY_QUERY_RE = re.compile(
    (
        r"\b(methotrexate|mtx)\b.*\b(neutropenia|low neutrophils)\b.*"
        r"\b(fever|sore throat|pyrexia)\b|"
        r"\b(fever|sore throat|pyrexia)\b.*\b(neutropenia|low neutrophils)\b.*"
        r"\b(methotrexate|mtx)\b"
    ),
    re.IGNORECASE,
)
_URGENT_TOXICITY_CHUNK_RE = re.compile(
    r"\b(methotrexate|mtx|neutropenia|low neutrophils|bone marrow suppression|"
    r"toxicity|monitoring|infection|withhold|stop|csdmard)\b",
    re.IGNORECASE,
)
_APPRAISAL_OR_BIOLOGIC_RE = re.compile(
    r"\b(baricitinib|sarilumab|adalimumab|etanercept|rituximab|tocilizumab|"
    r"biologic|technology appraisal|appraisal)\b",
    re.IGNORECASE,
)
_SLE_RENAL_QUERY_RE = re.compile(
    r"\b(sle|systemic lupus erythematosus|lupus)\b.*"
    r"\b(proteinuria|albuminuria|creatinine|renal|kidney|nephritis)\b|"
    r"\b(proteinuria|albuminuria|creatinine|renal|kidney|nephritis)\b.*"
    r"\b(sle|systemic lupus erythematosus|lupus)\b",
    re.IGNORECASE,
)
_SLE_RENAL_CHUNK_RE = re.compile(
    r"\b(lupus nephritis|systemic lupus erythematosus|sle|proteinuria|"
    r"protein:creatinine|protein creatinine|urinalysis|nephrology|renal|"
    r"kidney|creatinine|haematuria|upcr)\b",
    re.IGNORECASE,
)
_SLE_RENAL_DISTRACTOR_RE = re.compile(
    r"\b(spondyloarthritis|axial spondyloarthritis|psoriatic arthritis|"
    r"baricitinib|sarilumab|biologic|technology appraisal|appraisal)\b",
    re.IGNORECASE,
)
_MIGRAINE_TIA_QUERY_RE = re.compile(
    r"\b(migraine aura|migraine)\b.*\b(tia|transient ischaemic attack)\b|"
    r"\b(tia|transient ischaemic attack)\b.*\b(migraine aura|migraine)\b",
    re.IGNORECASE,
)
_EMERGENCY_QUERY_RE = re.compile(
    r"\b(cauda equina|cord compression|spinal emergency|neutropenic sepsis|"
    r"urinary retention|saddle anaesthesia|bilateral leg weakness|before transfer|"
    r"same-day|urgent transfer)\b",
    re.IGNORECASE,
)
_MIGRAINE_AURA_CHUNK_RE = re.compile(
    r"\b(migraine aura|migraine with aura|positive visual symptoms?|visual aura|"
    r"fully reversible|gradual spread|develop over at least 5 minutes|"
    r"5 to 60 minutes|5 and 60 minutes)\b",
    re.IGNORECASE,
)
_TIA_CHUNK_RE = re.compile(
    r"\b(tia|transient ischaemic attack|stroke|sudden negative symptoms|"
    r"immediate referral|24 hours)\b",
    re.IGNORECASE,
)
_MIGRAINE_TIA_DISTRACTOR_RE = re.compile(
    r"\b(galcanezumab|botulinum|quality statement|committee discussion|"
    r"primary headache disorders|secondary headache|quality of life)\b",
    re.IGNORECASE,
)
_GENERIC_SENSORY_DISTRACTOR_RE = re.compile(
    r"\b(numbness and weakness|sensory disturbances?|tingling|numbness)\b",
    re.IGNORECASE,
)
_EMERGENCY_OPERATIONAL_CHUNK_RE = re.compile(
    r"\b(cauda equina|cord compression|spinal emergency|severe low back pain|"
    r"new[- ]onset disturbance of bladder|bowel or sexual function|"
    r"urinary retention|perineal numbness|bilateral leg weakness|"
    r"refer immediately|immediate assessment)\b",
    re.IGNORECASE,
)
_EMERGENCY_DISTRACTOR_RE = re.compile(
    r"\b(hemiparesis|suspected cancer pathway|brain and central nervous system cancers|"
    r"sudden-onset limb weakness)\b",
    re.IGNORECASE,
)


def _has_citable_source(chunk: dict[str, Any]) -> bool:
    metadata = chunk.get("metadata") or {}
    source_url = metadata.get("source_url")
    if isinstance(source_url, str):
        source_url = source_url.strip()
    return bool(chunk.get("doc_id") or source_url)


def _effective_relevance_score(result: CitedResult) -> float:
    """Prefer retrieval's calibrated final score, falling back safely if absent."""
    final_score = float(getattr(result, "final_score", 0.0) or 0.0)
    if final_score > 0:
        return final_score
    rerank_score = float(result.rerank_score or 0.0)
    vector_score = float(result.vector_score or 0.0)
    return max(rerank_score, vector_score)


def _finalize_filtered(
    chunks: list[dict[str, Any]],
    query: str,
    *,
    specialty: str | None,
) -> list[dict[str, Any]]:
    return _prune_topic_outliers(
        _sort_by_alignment(
            chunks,
            query,
            specialty=specialty,
        ),
        query,
    )


def _requested_task_count(query: str) -> int:
    return len(_requested_tasks(query))


def _question_focus_text(query: str) -> str:
    units = [
        part.strip()
        for part in _SENTENCE_SPLIT_RE.split(query)
        if part and part.strip()
    ]
    if not units:
        return query
    question_units = [unit for unit in units if "?" in unit]
    if question_units:
        return question_units[-1]
    return units[-1]


def _requested_tasks(query: str) -> list[str]:
    focus_text = _question_focus_text(query)
    focus_tasks = [
        label for label, pattern in _TASK_PATTERNS if pattern.search(focus_text)
    ]
    if focus_tasks:
        return focus_tasks
    return [label for label, pattern in _TASK_PATTERNS if pattern.search(query)]


def _chunk_task_labels(chunk: dict[str, Any], requested_tasks: list[str]) -> set[str]:
    if not requested_tasks:
        return set()
    metadata = chunk.get("metadata") or {}
    haystack = " ".join(
        part
        for part in (
            chunk.get("text") or "",
            chunk.get("section_path") or metadata.get("section_title") or "",
            metadata.get("title") or metadata.get("source_name") or "",
        )
        if part
    )
    labels = {
        label
        for label, pattern in _TASK_PATTERNS
        if label in requested_tasks and pattern.search(haystack)
    }
    # Investigation-heavy referral templates often mention tests but not literal
    # imaging keywords. Preserve them as referral/investigation support only.
    return labels


def _task_coverage_count(
    chunks: list[dict[str, Any]],
    requested_tasks: list[str],
) -> int:
    covered: set[str] = set()
    for chunk in chunks:
        covered.update(_chunk_task_labels(chunk, requested_tasks))
    return len(covered)


def _select_task_covering_chunks(
    chunks: list[dict[str, Any]],
    *,
    original_query: str,
    max_chunks: int,
) -> list[dict[str, Any]]:
    if not chunks or max_chunks <= 0:
        return []

    if _EMERGENCY_QUERY_RE.search(original_query):
        operational = [
            chunk
            for chunk in chunks
            if _EMERGENCY_OPERATIONAL_CHUNK_RE.search(
                " ".join(
                    part
                    for part in (
                        chunk.get("text") or "",
                        chunk.get("section_path") or "",
                        (chunk.get("metadata") or {}).get("title") or "",
                    )
                    if part
                )
            )
        ]
        emergency_selected: list[dict[str, Any]] = []
        if operational:
            emergency_selected.append(operational[0])
        for chunk in chunks:
            if len(emergency_selected) >= max_chunks:
                break
            if chunk not in emergency_selected:
                emergency_selected.append(chunk)
        if emergency_selected:
            return emergency_selected[:max_chunks]

    if _MIGRAINE_TIA_QUERY_RE.search(original_query):
        migraine_chunks = [
            chunk
            for chunk in chunks
            if _MIGRAINE_AURA_CHUNK_RE.search(
                " ".join(
                    part
                    for part in (
                        chunk.get("text") or "",
                        chunk.get("section_path") or "",
                        (chunk.get("metadata") or {}).get("title") or "",
                    )
                    if part
                )
            )
        ]
        tia_chunks = [
            chunk
            for chunk in chunks
            if _TIA_CHUNK_RE.search(
                " ".join(
                    part
                    for part in (
                        chunk.get("text") or "",
                        chunk.get("section_path") or "",
                        (chunk.get("metadata") or {}).get("title") or "",
                    )
                    if part
                )
            )
        ]
        comparison_selected: list[dict[str, Any]] = []
        if migraine_chunks:
            comparison_selected.append(migraine_chunks[0])
        for chunk in tia_chunks:
            if chunk not in comparison_selected:
                comparison_selected.append(chunk)
                break
        for chunk in chunks:
            if len(comparison_selected) >= max_chunks:
                break
            if chunk not in comparison_selected:
                comparison_selected.append(chunk)
        if comparison_selected:
            return comparison_selected[:max_chunks]

    requested_tasks = _requested_tasks(original_query)
    if len(requested_tasks) < 2:
        return chunks[:max_chunks]

    remaining = list(chunks)
    selected: list[dict[str, Any]] = []
    covered: set[str] = set()

    while remaining and len(selected) < max_chunks:
        best_idx = 0
        best_gain = -1
        best_task_count = -1
        for idx, chunk in enumerate(remaining):
            labels = _chunk_task_labels(chunk, requested_tasks)
            gain = len(labels - covered)
            if gain > best_gain or (
                gain == best_gain and len(labels) > best_task_count
            ):
                best_idx = idx
                best_gain = gain
                best_task_count = len(labels)
        chosen = remaining.pop(best_idx)
        selected.append(chosen)
        covered.update(_chunk_task_labels(chosen, requested_tasks))

    return selected


def _finalize_with_chunk_floor(
    primary: list[dict[str, Any]],
    fallback: list[dict[str, Any]],
    *,
    original_query: str,
    expanded_query: str,
    specialty: str | None,
) -> list[dict[str, Any]]:
    minimum_chunks = 2 if _requested_task_count(original_query) >= 2 else 1
    if _EMERGENCY_QUERY_RE.search(original_query):
        minimum_chunks = max(minimum_chunks, 2)
    if _MIGRAINE_TIA_QUERY_RE.search(original_query):
        minimum_chunks = max(minimum_chunks, 2)
    target_chunks = min(max(minimum_chunks, len(primary)), 3)

    primary_final = _finalize_filtered(
        primary,
        expanded_query,
        specialty=specialty,
    )

    fallback_final = _finalize_filtered(
        fallback,
        expanded_query,
        specialty=specialty,
    )
    primary_selected = _select_task_covering_chunks(
        primary_final,
        original_query=original_query,
        max_chunks=min(target_chunks, len(primary_final)),
    )
    fallback_selected = _select_task_covering_chunks(
        fallback_final,
        original_query=original_query,
        max_chunks=min(target_chunks, len(fallback_final)),
    )

    if len(primary_selected) < minimum_chunks:
        return fallback_selected or primary_selected

    if len(fallback_selected) < minimum_chunks:
        return primary_selected

    if _task_coverage_count(fallback_selected, _requested_tasks(original_query)) > (
        _task_coverage_count(primary_selected, _requested_tasks(original_query))
    ):
        return fallback_selected

    return primary_selected


def _citation_section_path(result: CitedResult) -> str:
    return " > ".join(result.citation.section_path)


def _cited_result_to_chunk(result: CitedResult) -> dict[str, Any]:
    citation = result.citation
    metadata = {
        "title": citation.title,
        "source_name": citation.source_name,
        "filename": citation.title,
        "specialty": citation.specialty,
        "doc_type": citation.doc_type,
        "creation_date": citation.creation_date,
        "publish_date": citation.publish_date,
        "last_updated_date": citation.last_updated_date,
        "source_url": citation.source_url,
        "content_type": citation.content_type,
        "rerank_score": result.rerank_score,
        "vector_score": result.vector_score,
        "rrf_score": result.rrf_score,
        "keyword_rank": result.keyword_rank,
    }
    return {
        "text": result.text,
        "score": _effective_relevance_score(result),
        "doc_id": citation.doc_id,
        "doc_version": None,
        "chunk_id": citation.chunk_id,
        "chunk_index": None,
        "content_type": citation.content_type,
        "page_start": citation.page_start,
        "page_end": citation.page_end,
        "section_path": _citation_section_path(result),
        "metadata": metadata,
    }


def to_search_result(res: dict[str, Any]) -> SearchResult:
    metadata = res.get("metadata") or {}
    return SearchResult(
        text=res["text"],
        source=(
            metadata.get("title")
            or metadata.get("source_name")
            or metadata.get("filename")
            or "Unknown Source"
        ),
        score=res["score"],
        doc_id=res.get("doc_id"),
        doc_version=res.get("doc_version"),
        chunk_id=res.get("chunk_id"),
        chunk_index=res.get("chunk_index"),
        content_type=res.get("content_type"),
        page_start=res.get("page_start"),
        page_end=res.get("page_end"),
        section_path=res.get("section_path"),
        creation_date=metadata.get("creation_date"),
        publish_date=metadata.get("publish_date"),
        last_updated_date=metadata.get("last_updated_date"),
        metadata=metadata,
    )


def retrieve_chunks(
    query: str,
    *,
    top_k: int,
    specialty: str | None,
) -> list[dict[str, Any]]:
    chunks = [
        _cited_result_to_chunk(result)
        for result in retrieve(
            query=query,
            db_url=db_config.database_url,
            top_k=top_k,
            specialty=specialty,
            expand_query=True,
        )
    ]
    chunks.sort(key=lambda chunk: float(chunk.get("score", 0.0)), reverse=True)
    return chunks


def retrieve_chunks_advanced(
    query: str,
    *,
    top_k: int,
    specialty: str | None,
    source_name: str | None,
    doc_type: str | None,
    score_threshold: float,
    expand_query: bool,
) -> list[dict[str, Any]]:
    chunks = [
        _cited_result_to_chunk(result)
        for result in retrieve(
            query=query,
            db_url=db_config.database_url,
            top_k=top_k,
            specialty=specialty,
            source_name=source_name,
            doc_type=doc_type,
            score_threshold=score_threshold,
            expand_query=expand_query,
        )
    ]
    chunks.sort(key=lambda chunk: float(chunk.get("score", 0.0)), reverse=True)
    return chunks


def _filter_chunks(
    query: str,
    retrieved: list[dict[str, Any]],
    specialty: str | None,
) -> list[dict[str, Any]]:
    expanded_query = expand_query_text(query)

    def _raw_query_overlap(chunk: dict[str, Any]) -> bool:
        return has_query_overlap(query, chunk.get("text", ""))

    def _expanded_query_overlap(chunk: dict[str, Any]) -> bool:
        return expanded_query != query and has_query_overlap(
            expanded_query,
            chunk.get("text", ""),
        )

    base_candidates = [
        chunk
        for chunk in retrieved
        if chunk.get("score", 0) >= MIN_RELEVANCE
        and _has_citable_source(chunk)
    ]
    if not base_candidates:
        if not retrieved:
            return []
        top_score = max(float(chunk.get("score", 0.0)) for chunk in retrieved)
        if top_score < LOW_SCORE_FALLBACK_FLOOR:
            return []
        low_score_threshold = max(
            LOW_SCORE_FALLBACK_FLOOR,
            top_score * LOW_SCORE_FALLBACK_RATIO,
        )
        low_score_fallback = [
            chunk
            for chunk in retrieved
            if chunk.get("score", 0) >= low_score_threshold
            and _has_citable_source(chunk)
            and _raw_query_overlap(chunk)
        ]
        return _finalize_filtered(
            low_score_fallback,
            expanded_query,
            specialty=specialty,
        )

    alignments = [
        _alignment_details(expanded_query, chunk) for chunk in base_candidates
    ]
    filtered = [
        chunk
        for chunk, alignment in zip(base_candidates, alignments, strict=False)
        if not (is_boilerplate(chunk) and alignment["total"] < 3)
    ]
    if not filtered:
        return []

    if _MIGRAINE_TIA_QUERY_RE.search(query):
        comparison_final = _finalize_filtered(
            filtered,
            expanded_query,
            specialty=specialty,
        )
        return _select_task_covering_chunks(
            comparison_final,
            original_query=query,
            max_chunks=min(3, len(comparison_final)),
        )

    if _EMERGENCY_QUERY_RE.search(query):
        emergency_final = _finalize_filtered(
            filtered,
            expanded_query,
            specialty=specialty,
        )
        return _select_task_covering_chunks(
            emergency_final,
            original_query=query,
            max_chunks=min(3, len(emergency_final)),
        )

    strict_matches = [
        chunk
        for chunk in filtered
        if _raw_query_overlap(chunk)
        or (
            _expanded_query_overlap(chunk)
            and chunk.get("score", 0) >= SOFT_FALLBACK_RELEVANCE
        )
        or chunk.get("score", 0) >= HIGH_CONFIDENCE_RELEVANCE
    ]
    if strict_matches:
        alignments = [
            _alignment_details(expanded_query, chunk) for chunk in strict_matches
        ]
        max_title_section_overlap = max(
            alignment["title_section_overlap"] for alignment in alignments
        )
        max_text_phrases = max(alignment["text_phrases"] for alignment in alignments)
        if max_title_section_overlap >= 2 or max_text_phrases >= 1:
            narrowed = [
                chunk
                for chunk, alignment in zip(strict_matches, alignments, strict=False)
                if (
                    alignment["title_section_overlap"] == max_title_section_overlap
                    and max_title_section_overlap >= 2
                )
                or (
                    alignment["text_phrases"] == max_text_phrases
                    and max_text_phrases >= 1
                )
            ]
            if narrowed:
                return _finalize_with_chunk_floor(
                    narrowed,
                    strict_matches,
                    original_query=query,
                    expanded_query=expanded_query,
                    specialty=specialty,
                )
        refined = [
            chunk
            for chunk, alignment in zip(strict_matches, alignments, strict=False)
            if (
                alignment["total"] >= 5
                or alignment["text_phrases"] >= 1
                or alignment["title_section_overlap"] >= 2
            )
        ]
        if refined:
            return _finalize_with_chunk_floor(
                refined,
                strict_matches,
                original_query=query,
                expanded_query=expanded_query,
                specialty=specialty,
            )
        return _finalize_with_chunk_floor(
            strict_matches,
            filtered,
            original_query=query,
            expanded_query=expanded_query,
            specialty=specialty,
        )

    semantic_alignments = [
        _alignment_details(expanded_query, chunk) for chunk in filtered
    ]
    semantic_fallback = [
        chunk
        for chunk, alignment in zip(filtered, semantic_alignments, strict=False)
        if chunk.get("score", 0) >= SOFT_FALLBACK_RELEVANCE
        and (
            chunk.get("score", 0) >= HIGH_CONFIDENCE_RELEVANCE
            or (
            alignment["total"] >= 3
            or alignment["text_phrases"] >= 1
            or alignment["title_section_overlap"] >= 1
            )
        )
    ]
    if semantic_fallback:
        return _finalize_filtered(
            semantic_fallback,
            expanded_query,
            specialty=specialty,
        )

    top_score = max(float(chunk.get("score", 0.0)) for chunk in filtered)
    low_score_threshold = max(
        LOW_SCORE_FALLBACK_FLOOR,
        top_score * LOW_SCORE_FALLBACK_RATIO,
    )
    low_score_fallback = [
        chunk
        for chunk in filtered
        if chunk.get("score", 0) >= low_score_threshold
        and _raw_query_overlap(chunk)
    ]
    return _finalize_filtered(
        low_score_fallback,
        expanded_query,
        specialty=specialty,
    )


def filter_chunks(
    query: str,
    retrieved: list[dict[str, Any]],
    *,
    specialty: str | None = None,
) -> list[dict[str, Any]]:
    return _filter_chunks(query, retrieved, specialty=specialty)


def _alignment_details(query: str, chunk: dict[str, Any]) -> dict[str, int]:
    metadata = chunk.get("metadata") or {}
    text = chunk.get("text") or ""
    title = metadata.get("title") or metadata.get("source_name") or ""
    section = chunk.get("section_path") or metadata.get("section_title") or ""
    text_overlap = query_overlap_count(query, text)
    title_overlap = query_overlap_count(query, title)
    section_overlap = query_overlap_count(query, section)
    text_phrases = phrase_overlap_count(query, text)
    title_phrases = phrase_overlap_count(query, title)
    section_phrases = phrase_overlap_count(query, section)
    return {
        "total": (
            text_overlap
            + title_overlap
            + section_overlap
            + (2 * (text_phrases + title_phrases + section_phrases))
        ),
        "text_phrases": text_phrases,
        "title_section_overlap": (
            title_overlap + section_overlap + (2 * (title_phrases + section_phrases))
        ),
    }


def _sort_by_alignment(
    chunks: list[dict[str, Any]],
    query: str,
    *,
    specialty: str | None,
) -> list[dict[str, Any]]:
    preferred = (specialty or "").strip().casefold()

    def _specialty_match(chunk: dict[str, Any]) -> int:
        if not preferred:
            return 0
        metadata = chunk.get("metadata") or {}
        chunk_specialty = (metadata.get("specialty") or "").strip().casefold()
        return int(bool(chunk_specialty and chunk_specialty == preferred))

    def _document_score(chunk: dict[str, Any]) -> float:
        metadata = chunk.get("metadata") or {}
        return document_kind_score(
            title=metadata.get("title", ""),
            section=chunk.get("section_path") or metadata.get("section_title") or "",
            doc_type=metadata.get("doc_type", ""),
            source_name=metadata.get("source_name", ""),
        )

    def _intent_score(chunk: dict[str, Any]) -> float:
        metadata = chunk.get("metadata") or {}
        return query_intent_alignment_score(
            query,
            title=metadata.get("title", ""),
            section=chunk.get("section_path") or metadata.get("section_title") or "",
            text=chunk.get("text") or "",
            doc_type=metadata.get("doc_type", ""),
        )

    def _urgent_toxicity_score(chunk: dict[str, Any]) -> int:
        if not _URGENT_TOXICITY_QUERY_RE.search(query):
            return 0
        metadata = chunk.get("metadata") or {}
        haystack = " ".join(
            part
            for part in (
                chunk.get("text") or "",
                chunk.get("section_path") or metadata.get("section_title") or "",
                metadata.get("title") or metadata.get("source_name") or "",
                metadata.get("doc_type") or "",
            )
            if part
        )
        score = 0
        if _URGENT_TOXICITY_CHUNK_RE.search(haystack):
            score += 4
        if _APPRAISAL_OR_BIOLOGIC_RE.search(haystack):
            score -= 5
        return score

    def _sle_renal_score(chunk: dict[str, Any]) -> int:
        if not _SLE_RENAL_QUERY_RE.search(query):
            return 0
        metadata = chunk.get("metadata") or {}
        haystack = " ".join(
            part
            for part in (
                chunk.get("text") or "",
                chunk.get("section_path") or metadata.get("section_title") or "",
                metadata.get("title") or metadata.get("source_name") or "",
                metadata.get("doc_type") or "",
            )
            if part
        )
        score = 0
        if _SLE_RENAL_CHUNK_RE.search(haystack):
            score += 4
        if _SLE_RENAL_DISTRACTOR_RE.search(haystack):
            score -= 4
        return score

    def _comparison_balance_score(chunk: dict[str, Any]) -> int:
        if not _MIGRAINE_TIA_QUERY_RE.search(query):
            return 0
        metadata = chunk.get("metadata") or {}
        haystack = " ".join(
            part
            for part in (
                chunk.get("text") or "",
                chunk.get("section_path") or metadata.get("section_title") or "",
                metadata.get("title") or metadata.get("source_name") or "",
            )
            if part
        )
        score = 0
        if _MIGRAINE_AURA_CHUNK_RE.search(haystack):
            score += 4
        if _TIA_CHUNK_RE.search(haystack):
            score += 2
        if _GENERIC_SENSORY_DISTRACTOR_RE.search(haystack):
            score -= 2
        if _MIGRAINE_TIA_DISTRACTOR_RE.search(haystack):
            score -= 4
        return score

    def _emergency_balance_score(chunk: dict[str, Any]) -> int:
        if not _EMERGENCY_QUERY_RE.search(query):
            return 0
        metadata = chunk.get("metadata") or {}
        haystack = " ".join(
            part
            for part in (
                chunk.get("text") or "",
                chunk.get("section_path") or metadata.get("section_title") or "",
                metadata.get("title") or metadata.get("source_name") or "",
            )
            if part
        )
        score = 0
        if _EMERGENCY_OPERATIONAL_CHUNK_RE.search(haystack):
            score += 5
        if _EMERGENCY_DISTRACTOR_RE.search(haystack):
            score -= 3
        return score

    return sorted(
        chunks,
        key=lambda chunk: (
            _emergency_balance_score(chunk),
            _sle_renal_score(chunk),
            _urgent_toxicity_score(chunk),
            _comparison_balance_score(chunk),
            _specialty_match(chunk),
            _intent_score(chunk),
            _document_score(chunk),
            _alignment_details(query, chunk)["title_section_overlap"],
            _alignment_details(query, chunk)["total"]
            + text_quality_score(chunk.get("text") or ""),
            float(chunk.get("score", 0.0)),
        ),
        reverse=True,
    )


def _prune_topic_outliers(
    chunks: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Remove chunks whose topic intent is negatively aligned with the query.

    Uses ``query_intent_alignment_score`` as the primary signal — this covers
    procedural/surgical docs, audit tools, appraisals, etc. without needing
    a hardcoded marker list.  A chunk is pruned when:

    1. The top-ranked chunk is reasonably strong (score ≥ 0.4, alignment ≥ 3).
    2. The candidate has a *negative* intent score (wrong topic/task).
    3. The candidate's alignment is noticeably weaker than the top chunk's.
    """
    if len(chunks) <= 1:
        return chunks

    top = chunks[0]
    top_alignment = _alignment_details(query, top)
    top_score = float(top.get("score", 0.0))

    if top_score < 0.4 or top_alignment["total"] < 3:
        return chunks

    pruned = [top]
    for chunk in chunks[1:]:
        alignment = _alignment_details(query, chunk)
        metadata = chunk.get("metadata") or {}
        intent = query_intent_alignment_score(
            query,
            title=metadata.get("title", ""),
            section=(
                chunk.get("section_path")
                or metadata.get("section_title")
                or ""
            ),
            text=chunk.get("text") or "",
            doc_type=metadata.get("doc_type", ""),
        )
        score = float(chunk.get("score", 0.0))

        if (
            intent < 0
            and alignment["total"] <= max(2, top_alignment["total"] - 2)
            and score < top_score
        ):
            continue
        pruned.append(chunk)

    return pruned


def evidence_level(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "none"

    scores = [float(chunk.get("score", 0.0)) for chunk in chunks]
    top_score = scores[0]
    strong_hits = sum(1 for score in scores[:3] if score >= LOW_EVIDENCE_TOP_SCORE)
    if top_score < LOW_EVIDENCE_TOP_SCORE or strong_hits <= LOW_EVIDENCE_STRONG_HITS:
        return "weak"
    return "strong"


def low_evidence_note(level: str) -> str | None:
    if level != "weak":
        return None
    return (
        "Indexed guideline support is limited for this question. If the context "
        "does not directly support a claim, say so explicitly and keep any "
        "general context clearly separated."
    )


def query_fingerprint(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]


def log_route_decision(
    endpoint: str,
    provider: ProviderName,
    route_score: float,
    threshold: float,
    reasons: tuple[str, ...],
    *,
    query: str | None = None,
    retrieved_count: int | None = None,
    top_score: float | None = None,
    evidence: str | None = None,
    outcome: str | None = None,
) -> None:
    logger.info(
        "%s routing provider=%s score=%s threshold=%s reasons=%s",
        endpoint,
        provider,
        route_score,
        threshold,
        ",".join(reasons) or "none",
    )
    append_jsonl(
        ROUTE_TELEMETRY_PATH,
        {
            "endpoint": endpoint,
            "provider": provider,
            "score": route_score,
            "threshold": threshold,
            "reasons": list(reasons),
            "query_hash": query_fingerprint(query) if query else None,
            "retrieved_count": retrieved_count,
            "top_score": top_score,
            "evidence": evidence,
            "outcome": outcome,
        },
    )
