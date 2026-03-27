"""
Retrieval quality test suite for GP queries and follow-up conversation scenarios.

Tests that:
1. Single standalone queries retrieve relevant chunks (core functionality)
2. Follow-up queries with conversation history retrieve contextually correct chunks
3. Results are consistent across repeated runs (each test runs retrieval twice)
4. Clinical accuracy: correct guidelines are surfaced for each condition

Covers guidelines across all ingested sources:
BSR, NICE, NICE_NEURO, OTHER_RHEUMATOLOGY.

Runs purely against the retrieval layer — no LLM generation — so results are
deterministic and fast.

Run with:
    .venv312/bin/python3 -m pytest tests/retrieval/test_followup_retrieval_quality.py -v
"""

from __future__ import annotations

import os
from typing import ClassVar

import pytest

# These tests require a live database with ingested clinical guideline chunks.
# Skip entirely in CI where no database is available.
pytestmark = pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="Retrieval quality tests require a live vector database with ingested chunks",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _augment(query: str, history: str | None) -> str:
    """Call the live _augment_query_with_history from routes.py."""
    from src.api.routes import _augment_query_with_history

    patient_context = {"conversation_history": history} if history else None
    return _augment_query_with_history(query, patient_context)


def _retrieve(query: str, top_k: int = 5) -> list[dict]:
    from src.api.services import retrieve_chunks_advanced

    return retrieve_chunks_advanced(
        query=query,
        top_k=top_k,
        specialty=None,
        source_name=None,
        doc_type=None,
        score_threshold=0.3,
        expand_query=False,
    )


def _merge(primary: list[dict], secondary: list[dict]) -> list[dict]:
    from src.api.routes import _merge_retrieved

    return _merge_retrieved(primary, secondary)


def _filter(query: str, chunks: list[dict]) -> list[dict]:
    from src.api.services import filter_chunks

    return filter_chunks(query, chunks)


def _full_pipeline(current_query: str, history: str | None) -> list[dict]:
    """Full pipeline: augment → dual-retrieve → merge → filter."""
    augmented = _augment(current_query, history)
    was_augmented = augmented != current_query

    primary = _retrieve(augmented)
    if was_augmented:
        secondary = _retrieve(current_query)
        merged = _merge(primary, secondary)
    else:
        merged = primary

    return _filter(current_query, merged)


def _history(*turns: str) -> str:
    return "\n".join(f"GP: {t}" for t in turns)


def _chunk_text_combined(chunks: list[dict], top_n: int = 5) -> str:
    """Combine text + metadata from top N chunks into one searchable string."""
    parts = []
    for c in chunks[:top_n]:
        meta = c.get("metadata", {})
        parts.append(
            f"{c.get('text', '')} {meta.get('title', '')} "
            f"{meta.get('source_name', '')} {c.get('section_path', '')}"
        )
    return " ".join(parts).lower()


def _has_keywords(chunks: list[dict], keywords: set[str], top_n: int = 5) -> bool:
    """True if any keyword appears in the combined text of the top N chunks."""
    combined = _chunk_text_combined(chunks, top_n)
    return any(kw in combined for kw in keywords)


def _top_title(chunks: list[dict]) -> str:
    if not chunks:
        return "NO_CHUNKS"
    return chunks[0].get("metadata", {}).get("title", "unknown")


def _titles(chunks: list[dict], n: int = 5) -> list[str]:
    return [c.get("metadata", {}).get("title", "?") for c in chunks[:n]]


def _assert_consistent(query: str, history: str | None, keywords: set[str]):
    """Run retrieval twice, check both return relevant results and share top source."""
    r1 = _full_pipeline(query, history)
    r2 = _full_pipeline(query, history)

    assert r1, f"Run 1 returned no chunks for: {query[:80]}"
    assert r2, f"Run 2 returned no chunks for: {query[:80]}"

    assert _has_keywords(r1, keywords), (
        f"Run 1: no relevant keyword in top-5. Titles: {_titles(r1)}"
    )
    assert _has_keywords(r2, keywords), (
        f"Run 2: no relevant keyword in top-5. Titles: {_titles(r2)}"
    )

    # Top source should be the same across both runs (consistency)
    assert _top_title(r1) == _top_title(r2), (
        f"Inconsistent top source: run1={_top_title(r1)!r} vs run2={_top_title(r2)!r}"
    )


# ============================================================================
# SECTION A: STANDALONE SINGLE QUERIES (core functionality, no history)
# Each condition covers a different ingested guideline source.
# ============================================================================


class TestStandalonePMR:
    """BSR source — Polymyalgia Rheumatica."""

    QUERY = (
        "70-year-old with sudden onset bilateral shoulder and hip girdle pain "
        "with morning stiffness >1 hour and raised ESR. "
        "Should polymyalgia rheumatica be started on steroids in primary care?"
    )
    KEYWORDS: ClassVar[set[str]] = {"polymyalgia", "pmr", "prednisolone", "shoulder"}

    def test_no_augmentation_without_history(self):
        assert _augment(self.QUERY, None) == self.QUERY
        assert _augment(self.QUERY, "") == self.QUERY

    def test_relevant_chunks_retrieved_consistently(self):
        _assert_consistent(self.QUERY, None, self.KEYWORDS)

    def test_top_source_is_bsr(self):
        chunks = _full_pipeline(self.QUERY, None)
        source = chunks[0].get("metadata", {}).get("source_name", "")
        assert source == "BSR", f"Expected BSR source, got {source!r}"


class TestStandaloneRheumatoidArthritis:
    """NICE source — Rheumatoid arthritis management."""

    QUERY = (
        "55-year-old woman with symmetrical small joint polyarthritis, "
        "positive rheumatoid factor and anti-CCP, raised CRP. "
        "What is the first-line DMARD for rheumatoid arthritis?"
    )
    KEYWORDS: ClassVar[set[str]] = {"rheumatoid", "dmard", "methotrexate", "arthritis"}

    def test_no_augmentation_without_history(self):
        assert _augment(self.QUERY, None) == self.QUERY

    def test_relevant_chunks_retrieved_consistently(self):
        _assert_consistent(self.QUERY, None, self.KEYWORDS)


class TestStandaloneGout:
    """NICE source — Gout management."""

    QUERY = (
        "45-year-old male presenting with acute monoarthritis of the first MTP "
        "joint, raised serum urate. How should acute gout be managed?"
    )
    KEYWORDS: ClassVar[set[str]] = {
        "gout",
        "urate",
        "colchicine",
        "nsaid",
        "allopurinol",
    }

    def test_relevant_chunks_retrieved_consistently(self):
        _assert_consistent(self.QUERY, None, self.KEYWORDS)


class TestStandaloneOsteoarthritis:
    """NICE source — Osteoarthritis."""

    QUERY = (
        "62-year-old with chronic knee pain worse on weight-bearing, "
        "morning stiffness <30 minutes, crepitus on examination. "
        "What are the recommended treatments for osteoarthritis of the knee?"
    )
    KEYWORDS: ClassVar[set[str]] = {
        "osteoarthritis",
        "exercise",
        "weight",
        "knee",
        "paracetamol",
        "nsaid",
    }

    def test_relevant_chunks_retrieved_consistently(self):
        _assert_consistent(self.QUERY, None, self.KEYWORDS)


class TestStandaloneAxialSpondyloarthritis:
    """NICE/BSR source — Axial spondyloarthritis."""

    QUERY = (
        "28-year-old man with inflammatory back pain for 6 months, "
        "worse at night and with morning stiffness >30 minutes, HLA-B27 positive. "
        "Should this patient be referred for suspected axial spondyloarthritis?"
    )
    KEYWORDS: ClassVar[set[str]] = {
        "spondyloarthritis",
        "axial",
        "hla-b27",
        "back pain",
        "biologic",
    }

    def test_relevant_chunks_retrieved_consistently(self):
        _assert_consistent(self.QUERY, None, self.KEYWORDS)


class TestStandaloneOsteoporosis:
    """NICE source — Osteoporosis / fracture risk."""

    QUERY = (
        "72-year-old postmenopausal woman with low-trauma wrist fracture, "
        "T-score -2.8 at lumbar spine. "
        "What bisphosphonate should be started for osteoporosis?"
    )
    KEYWORDS: ClassVar[set[str]] = {
        "osteoporosis",
        "bisphosphonate",
        "fracture",
        "alendronate",
        "bone",
    }

    def test_relevant_chunks_retrieved_consistently(self):
        _assert_consistent(self.QUERY, None, self.KEYWORDS)


class TestStandaloneLowBackPain:
    """NICE source — Low back pain and sciatica."""

    QUERY = (
        "40-year-old with 8 weeks of non-specific low back pain, no red flags. "
        "What does NICE recommend for management of non-specific low back pain?"
    )
    KEYWORDS: ClassVar[set[str]] = {
        "back pain",
        "sciatica",
        "exercise",
        "physiotherapy",
        "imaging",
    }

    def test_relevant_chunks_retrieved_consistently(self):
        _assert_consistent(self.QUERY, None, self.KEYWORDS)


class TestStandaloneMigraine:
    """NICE_NEURO source — Headache / migraine."""

    QUERY = (
        "35-year-old woman with recurrent unilateral throbbing headaches with "
        "nausea and photophobia lasting 4-72 hours. "
        "What is the acute treatment for migraine?"
    )
    KEYWORDS: ClassVar[set[str]] = {
        "migraine",
        "headache",
        "triptan",
        "acute",
        "nausea",
    }

    def test_relevant_chunks_retrieved_consistently(self):
        _assert_consistent(self.QUERY, None, self.KEYWORDS)


class TestStandaloneMultipleSclerosis:
    """NICE_NEURO source — Multiple sclerosis."""

    QUERY = (
        "32-year-old with two episodes of optic neuritis and periventricular "
        "white matter lesions on MRI. "
        "What disease-modifying therapies are recommended for relapsing-remitting MS?"
    )
    KEYWORDS: ClassVar[set[str]] = {
        "multiple sclerosis",
        "relapsing",
        "disease-modifying",
        "interferon",
        "fingolimod",
        "ocrelizumab",
    }

    def test_relevant_chunks_retrieved_consistently(self):
        _assert_consistent(self.QUERY, None, self.KEYWORDS)


class TestStandaloneEpilepsy:
    """NICE_NEURO source — Epilepsy."""

    QUERY = (
        "22-year-old with two unprovoked generalised tonic-clonic seizures. "
        "What is the first-line treatment for generalised epilepsy?"
    )
    KEYWORDS: ClassVar[set[str]] = {
        "epilepsy",
        "seizure",
        "valproate",
        "lamotrigine",
        "antiepileptic",
        "generalised",
    }

    def test_relevant_chunks_retrieved_consistently(self):
        _assert_consistent(self.QUERY, None, self.KEYWORDS)


class TestStandaloneParkinsons:
    """NICE_NEURO source — Parkinson's disease."""

    QUERY = (
        "67-year-old man with resting tremor, bradykinesia and rigidity. "
        "What is the initial pharmacological treatment for Parkinson's disease?"
    )
    KEYWORDS: ClassVar[set[str]] = {
        "parkinson",
        "levodopa",
        "dopamine",
        "tremor",
        "bradykinesia",
    }

    def test_relevant_chunks_retrieved_consistently(self):
        _assert_consistent(self.QUERY, None, self.KEYWORDS)


# ============================================================================
# SECTION B: FOLLOW-UP CONVERSATIONS
# Each scenario has 2-3 turns testing augmentation, retrieval, and consistency.
# ============================================================================

# --- Scenario 1: PMR → GCA emergency (the original bug) ---

PMR_QUERY = (
    "70-year-old with sudden onset bilateral shoulder and hip girdle pain "
    "with morning stiffness >1 hour and raised ESR. "
    "Should polymyalgia rheumatica be started on steroids in primary care?"
)
GCA_FOLLOWUP = (
    "She also mentions a new headache over the last 3 days "
    "and some jaw aching when chewing."
)
GCA_VISUAL_FOLLOWUP = (
    "Patient also has visual disturbances in the left eye since this morning."
)
GCA_DOSE_FOLLOWUP = "What dose should she receive?"


class TestFollowupPmrToGca:
    """PMR → GCA escalation: the core scenario this fix addresses."""

    def test_turn2_augmentation_triggered(self):
        history = _history(PMR_QUERY)
        result = _augment(GCA_FOLLOWUP, history)
        assert result != GCA_FOLLOWUP
        assert "shoulder" in result.lower() or "polymyalgia" in result.lower()

    def test_turn2_current_query_not_doubled(self):
        history = _history(PMR_QUERY, GCA_FOLLOWUP)
        result = _augment(GCA_FOLLOWUP, history)
        assert result.lower().count("jaw aching") == 1

    def test_turn2_gca_chunks_retrieved_consistently(self):
        history = _history(PMR_QUERY)
        gca_kw = {"giant cell", "temporal arteritis", "jaw claudication", "headache"}
        _assert_consistent(GCA_FOLLOWUP, history, gca_kw)

    def test_turn2_no_irrelevant_top_result(self):
        history = _history(PMR_QUERY)
        chunks = _full_pipeline(GCA_FOLLOWUP, history)
        assert chunks
        combined = _chunk_text_combined(chunks, 1)
        for bad in ["spondyloarthritis", "sjögren", "sjogren"]:
            assert bad not in combined, f"Top result is about irrelevant topic: {bad!r}"

    def test_turn3_visual_followup_consistent(self):
        history = _history(PMR_QUERY, GCA_FOLLOWUP)
        kw = {"giant cell", "temporal arteritis", "vision", "visual", "ophthalm"}
        _assert_consistent(GCA_VISUAL_FOLLOWUP, history, kw)

    def test_turn4_dose_augmentation_triggered(self):
        history = _history(PMR_QUERY, GCA_FOLLOWUP, GCA_VISUAL_FOLLOWUP)
        result = _augment(GCA_DOSE_FOLLOWUP, history)
        assert result != GCA_DOSE_FOLLOWUP

    def test_turn4_dose_clinical_chunks_consistent(self):
        history = _history(PMR_QUERY, GCA_FOLLOWUP, GCA_VISUAL_FOLLOWUP)
        kw = {"prednisolone", "dose", "steroid", "mg", "giant cell", "treatment"}
        _assert_consistent(GCA_DOSE_FOLLOWUP, history, kw)


# --- Scenario 2: RA → side effects follow-up ---

RA_QUERY = (
    "55-year-old woman started on methotrexate 15mg weekly for rheumatoid "
    "arthritis 3 months ago. What monitoring bloods are needed?"
)
RA_SIDE_EFFECTS_FOLLOWUP = (
    "She is also complaining of mouth ulcers and nausea since starting it."
)


class TestFollowupRaSideEffects:
    """RA initial → side effects follow-up: tests cross-turn context."""

    def test_turn1_ra_monitoring_consistent(self):
        kw = {"methotrexate", "monitoring", "blood", "fbc", "liver", "renal"}
        _assert_consistent(RA_QUERY, None, kw)

    def test_turn2_augmentation_triggered(self):
        history = _history(RA_QUERY)
        result = _augment(RA_SIDE_EFFECTS_FOLLOWUP, history)
        assert result != RA_SIDE_EFFECTS_FOLLOWUP
        assert "methotrexate" in result.lower()

    def test_turn2_side_effects_consistent(self):
        history = _history(RA_QUERY)
        kw = {
            "methotrexate",
            "side effect",
            "nausea",
            "mouth ulcer",
            "folic acid",
            "toxicity",
            "adverse",
        }
        _assert_consistent(RA_SIDE_EFFECTS_FOLLOWUP, history, kw)


# --- Scenario 3: Gout → chronic management follow-up ---

GOUT_QUERY = (
    "45-year-old male with third acute gout flare this year in the first MTP joint. "
    "Serum urate 520 micromol/L. How should I manage the acute flare?"
)
GOUT_FOLLOWUP = (
    "He also wants to know when to start allopurinol for long-term prevention."
)


class TestFollowupGoutChronic:
    """Acute gout → urate-lowering therapy follow-up."""

    def test_turn1_acute_gout_consistent(self):
        kw = {"gout", "acute", "colchicine", "nsaid", "flare"}
        _assert_consistent(GOUT_QUERY, None, kw)

    def test_turn2_augmentation_triggered(self):
        history = _history(GOUT_QUERY)
        result = _augment(GOUT_FOLLOWUP, history)
        assert result != GOUT_FOLLOWUP

    def test_turn2_ult_consistent(self):
        history = _history(GOUT_QUERY)
        kw = {
            "allopurinol",
            "urate",
            "ult",
            "urate-lowering",
            "febuxostat",
            "prophylaxis",
        }
        _assert_consistent(GOUT_FOLLOWUP, history, kw)


# --- Scenario 4: Low back pain → red flag follow-up ---

LBP_QUERY = (
    "40-year-old with 8 weeks of non-specific low back pain, no red flags. "
    "What does NICE recommend for management?"
)
LBP_RED_FLAG_FOLLOWUP = (
    "He now reports bilateral leg weakness and difficulty passing urine "
    "since yesterday."
)


class TestFollowupLbpCaudaEquina:
    """Low back pain → cauda equina red flag escalation."""

    def test_turn1_lbp_consistent(self):
        kw = {"back pain", "sciatica", "exercise", "physiotherapy"}
        _assert_consistent(LBP_QUERY, None, kw)

    def test_turn2_augmentation_triggered(self):
        history = _history(LBP_QUERY)
        result = _augment(LBP_RED_FLAG_FOLLOWUP, history)
        assert result != LBP_RED_FLAG_FOLLOWUP

    def test_turn2_cauda_equina_consistent(self):
        history = _history(LBP_QUERY)
        kw = {
            "cauda equina",
            "emergency",
            "bilateral",
            "weakness",
            "urinary",
            "neurosurgical",
            "spinal",
            "decompression",
            "red flag",
        }
        _assert_consistent(LBP_RED_FLAG_FOLLOWUP, history, kw)


# --- Scenario 5: Headache → stroke/TIA follow-up ---

HEADACHE_QUERY = (
    "58-year-old with new-onset severe headache reaching maximum intensity "
    "within 5 minutes. What are the red flag features I should check?"
)
HEADACHE_TIA_FOLLOWUP = (
    "She also had transient right arm weakness lasting about 20 minutes "
    "that has now resolved."
)


class TestFollowupHeadacheToTia:
    """Secondary headache → TIA suspicion follow-up."""

    def test_turn1_headache_red_flags_consistent(self):
        kw = {
            "headache",
            "secondary",
            "red flag",
            "sudden",
            "thunderclap",
            "subarachnoid",
            "neurological",
        }
        _assert_consistent(HEADACHE_QUERY, None, kw)

    def test_turn2_augmentation_triggered(self):
        history = _history(HEADACHE_QUERY)
        result = _augment(HEADACHE_TIA_FOLLOWUP, history)
        assert result != HEADACHE_TIA_FOLLOWUP

    def test_turn2_tia_consistent(self):
        history = _history(HEADACHE_QUERY)
        kw = {
            "transient",
            "tia",
            "stroke",
            "ischaemic",
            "weakness",
            "neurological",
            "aspirin",
            "referral",
        }
        _assert_consistent(HEADACHE_TIA_FOLLOWUP, history, kw)


# --- Scenario 6: Osteoporosis → fracture follow-up ---

OSTEO_QUERY = (
    "72-year-old postmenopausal woman on alendronate for 5 years, T-score "
    "now -2.0. Should the bisphosphonate be continued?"
)
OSTEO_FRACTURE_FOLLOWUP = (
    "She has also had a new vertebral fracture found on X-ray despite treatment."
)


class TestFollowupOsteoporosisFracture:
    """Osteoporosis management → treatment failure / fracture follow-up."""

    def test_turn1_osteoporosis_consistent(self):
        kw = {
            "osteoporosis",
            "bisphosphonate",
            "alendronate",
            "bone",
            "fracture",
            "t-score",
            "denosumab",
        }
        _assert_consistent(OSTEO_QUERY, None, kw)

    def test_turn2_augmentation_triggered(self):
        history = _history(OSTEO_QUERY)
        result = _augment(OSTEO_FRACTURE_FOLLOWUP, history)
        assert result != OSTEO_FRACTURE_FOLLOWUP

    def test_turn2_fracture_consistent(self):
        history = _history(OSTEO_QUERY)
        kw = {
            "fracture",
            "vertebral",
            "osteoporosis",
            "denosumab",
            "teriparatide",
            "treatment",
            "bisphosphonate",
        }
        _assert_consistent(OSTEO_FRACTURE_FOLLOWUP, history, kw)
