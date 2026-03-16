from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..config import routing_config

ProviderName = Literal["local", "cloud"]

_COMPLEXITY_TERMS = {
    "differential",
    "compare",
    "versus",
    "management",
    "investigation",
    "investigations",
    "contraindication",
    "contraindications",
    "comorbidity",
    "escalate",
    "stepwise",
    "algorithm",
}

_RISK_TERMS = {
    "urgent",
    "emergency",
    "acute",
    "sudden",
    "progressive",
    "rapidly progressive",
    "seizure",
    "weakness",
    "vision loss",
    "confusion",
    "vasculitis",
    "giant cell arteritis",
    "cord compression",
}


class RouteDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: ProviderName
    score: float
    threshold: float
    reasons: tuple[str, ...]


def select_generation_provider(
    *,
    query: str,
    retrieved_chunks: list[dict],
    severity: str | None = None,
    is_revision: bool = False,
    prompt_length_chars: int | None = None,
    threshold: float | None = None,
) -> RouteDecision:
    resolved_threshold = (
        routing_config.llm_route_threshold if threshold is None else threshold
    )
    if routing_config.force_cloud_llm:
        return RouteDecision(
            provider="cloud",
            score=1.0,
            threshold=resolved_threshold,
            reasons=("force_cloud_llm",),
        )

    reasons: list[str] = []
    score = 0.0

    complexity_score, complexity_reasons = _score_complexity(query)
    if complexity_score:
        score += complexity_score
        reasons.extend(complexity_reasons)

    prompt_score, prompt_reasons = _score_prompt_size(prompt_length_chars)
    if prompt_score:
        score += prompt_score
        reasons.extend(prompt_reasons)

    risk_score, risk_reasons = _score_risk(query, severity)
    if risk_score:
        score += risk_score
        reasons.extend(risk_reasons)

    ambiguity_score, ambiguity_reasons = _score_ambiguity(retrieved_chunks)
    if ambiguity_score:
        score += ambiguity_score
        reasons.extend(ambiguity_reasons)

    if is_revision and routing_config.route_revisions_to_cloud:
        reasons.append("revision_flow")
        score = max(score, resolved_threshold)

    score = min(score, 1.0)
    provider: ProviderName = "cloud" if score >= resolved_threshold else "local"
    return RouteDecision(
        provider=provider,
        score=round(score, 3),
        threshold=resolved_threshold,
        reasons=tuple(reasons),
    )


def _score_complexity(query: str) -> tuple[float, list[str]]:
    query_lower = query.lower()
    reasons: list[str] = []
    score = 0.0

    if len(query) >= 240:
        score += 0.18
        reasons.append("long_query")
    elif len(query) >= 140:
        score += 0.10
        reasons.append("medium_query")

    sentence_count = len([part for part in re.split(r"[.!?]+", query) if part.strip()])
    if sentence_count >= 3:
        score += 0.12
        reasons.append("multi_sentence")

    matched_terms = [term for term in _COMPLEXITY_TERMS if term in query_lower]
    if matched_terms:
        score += min(0.18, 0.06 * len(matched_terms))
        reasons.append("complex_reasoning_terms")

    return score, reasons


def _score_prompt_size(prompt_length_chars: int | None) -> tuple[float, list[str]]:
    if prompt_length_chars is None or prompt_length_chars <= 0:
        return 0.0, []

    score = 0.0
    reasons: list[str] = []

    if prompt_length_chars >= routing_config.long_prompt_chars:
        score += 0.70
        reasons.append("long_prompt")
    elif prompt_length_chars >= routing_config.medium_prompt_chars:
        score += 0.30
        reasons.append("medium_prompt")

    return score, reasons


def _score_risk(query: str, severity: str | None) -> tuple[float, list[str]]:
    query_lower = query.lower()
    reasons: list[str] = []
    score = 0.0

    if severity in {"urgent", "emergency"}:
        score += 0.30 if severity == "urgent" else 0.40
        reasons.append(f"severity_{severity}")

    matched_terms = [term for term in _RISK_TERMS if term in query_lower]
    if matched_terms:
        score += min(0.30, 0.08 * len(matched_terms))
        reasons.append("clinical_risk_terms")

    return score, reasons


def _score_ambiguity(retrieved_chunks: list[dict]) -> tuple[float, list[str]]:
    if not retrieved_chunks:
        return 0.22, ["no_retrieval_hits"]

    scores = [float(chunk.get("score", 0.0)) for chunk in retrieved_chunks]
    top_score = scores[0]
    reasons: list[str] = []
    score = 0.0

    if top_score < 0.35:
        score += 0.22
        reasons.append("low_top_score")
    elif top_score < 0.45:
        score += 0.12
        reasons.append("moderate_top_score")

    if len(scores) >= 2:
        gap = scores[0] - scores[1]
        if gap < 0.03:
            score += 0.14
            reasons.append("small_top_gap")
        elif gap < 0.06:
            score += 0.08
            reasons.append("moderate_top_gap")

    strong_hits = sum(1 for value in scores[:3] if value >= 0.45)
    if strong_hits <= 1:
        score += 0.10
        reasons.append("few_strong_hits")

    return score, reasons
