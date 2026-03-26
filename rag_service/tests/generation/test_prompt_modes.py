from src.generation.prompts import (
    allows_uncited_answer,
    build_grounded_prompt,
    build_revision_prompt,
    select_answer_mode,
)

_CHUNKS = [
    {
        "text": "Refer adults with rapidly progressive gait disturbance.",
        "metadata": {"title": "Neurology referral guidance"},
        "score": 0.9,
        "page_start": 11,
        "page_end": 12,
    }
]


def test_select_answer_mode_always_returns_strict_guideline() -> None:
    """Answer mode routing is now a no-op — always returns strict_guideline."""
    mode = select_answer_mode(
        "48-year-old with new onset severe back pain and bilateral leg weakness "
        "with urinary retention. What immediate steps are required before transfer?"
    )
    assert mode == "strict_guideline"

    mode = select_answer_mode(
        "How can migraine aura be distinguished from TIA in primary care?"
    )
    assert mode == "strict_guideline"


def test_allows_uncited_answer_always_true() -> None:
    """The simplified pipeline always allows answers through."""
    assert allows_uncited_answer("strict_guideline", evidence_level="weak") is True
    assert allows_uncited_answer("strict_guideline", evidence_level="strong") is True
    assert allows_uncited_answer("comparison", evidence_level="weak") is True


def test_grounded_prompt_uses_unified_instructions() -> None:
    prompt = build_grounded_prompt(
        "Need urgent transfer advice",
        _CHUNKS,
    )

    assert "clinical decision-support assistant for a GP" in prompt
    assert "Cite supporting passages" in prompt
    assert "Do not fabricate" in prompt
    assert "Do NOT add a summary paragraph" in prompt


def test_grounded_prompt_uses_simpler_context_format() -> None:
    prompt = build_grounded_prompt(
        "How can migraine aura be distinguished from TIA?",
        _CHUNKS,
    )

    assert "Source:" not in prompt
    assert "Match cues:" not in prompt
    assert "[1] Neurology referral guidance" in prompt


def test_grounded_prompt_includes_patient_context() -> None:
    prompt = build_grounded_prompt(
        "What investigations should I order?",
        _CHUNKS,
        patient_context={"age": 45, "gender": "female", "specialty": "neurology"},
    )

    assert "Age: 45" in prompt
    assert "Gender: Female" in prompt
    assert "Specialty: Neurology" in prompt


def test_grounded_prompt_includes_file_context() -> None:
    prompt = build_grounded_prompt(
        "Summarise this document.",
        _CHUNKS,
        file_context="Uploaded document content here.",
    )

    assert "UPLOADED DOCUMENTS" in prompt
    assert "Uploaded document content here." in prompt


def test_grounded_prompt_no_context_produces_none_marker() -> None:
    prompt = build_grounded_prompt("What is X?", [])

    assert "Context:\n(none)" in prompt
    assert "Answer (no citations):" in prompt


def test_revision_prompt_includes_feedback() -> None:
    prompt = build_revision_prompt(
        original_question="What about X?",
        previous_answer="Some answer.",
        specialist_feedback="Add more detail.",
        chunks=_CHUNKS,
    )

    assert "specialist" in prompt.lower()
    assert "Add more detail." in prompt
    assert "Some answer." in prompt
    assert "Revised answer (with citations):" in prompt


def test_grounded_prompt_answer_mode_ignored() -> None:
    """Answer mode parameter is accepted but has no effect on prompt."""
    prompt_default = build_grounded_prompt("Q?", _CHUNKS)
    prompt_emergency = build_grounded_prompt("Q?", _CHUNKS, answer_mode="emergency")

    # Both should produce the same prompt since mode routing is disabled.
    assert prompt_default == prompt_emergency
