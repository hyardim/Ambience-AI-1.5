from src.generation.prompts import (
    allows_uncited_answer,
    build_grounded_prompt,
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


def test_select_answer_mode_detects_emergency_queries() -> None:
    mode = select_answer_mode(
        "48-year-old with new onset severe back pain and bilateral leg weakness "
        "with urinary retention. What immediate steps are required before transfer?"
    )

    assert mode == "emergency"


def test_select_answer_mode_detects_comparison_queries() -> None:
    mode = select_answer_mode(
        "How can migraine aura be distinguished from TIA in primary care?"
    )

    assert mode == "comparison"


def test_select_answer_mode_detects_routine_low_risk_queries() -> None:
    mode = select_answer_mode(
        "29-year-old with intermittent hand tremor worse with anxiety and caffeine. "
        "No rigidity, bradykinesia, or neurological deficit. "
        "What initial management is appropriate before referral?"
    )

    assert mode == "routine_low_risk"


def test_select_answer_mode_detects_partial_support_workup_queries() -> None:
    mode = select_answer_mode(
        "35-year-old with intermittent joint swelling in knees and wrists over "
        "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
        "tests and imaging should be completed prior to referral?"
    )

    assert mode == "routine_low_risk"


def test_allows_uncited_answer_for_routine_low_risk_mode() -> None:
    assert allows_uncited_answer("routine_low_risk", evidence_level="weak") is True


def test_allows_uncited_answer_only_for_weak_comparison_mode() -> None:
    assert allows_uncited_answer("comparison", evidence_level="weak") is True
    assert allows_uncited_answer("comparison", evidence_level="strong") is False


def test_grounded_prompt_includes_emergency_mode_instructions() -> None:
    prompt = build_grounded_prompt(
        "Need urgent transfer advice",
        _CHUNKS,
        answer_mode="emergency",
    )

    assert "EMERGENCY MODE" in prompt
    assert "Immediate action:" in prompt
    assert "ANSWER MODE\nemergency" in prompt


def test_grounded_prompt_includes_comparison_mode_instructions() -> None:
    prompt = build_grounded_prompt(
        "How can migraine aura be distinguished from TIA?",
        _CHUNKS,
        answer_mode="comparison",
    )

    assert "COMPARISON MODE" in prompt
    assert "Key differences:" in prompt
    assert "ANSWER MODE\ncomparison" in prompt


def test_grounded_prompt_includes_grounding_guardrails() -> None:
    prompt = build_grounded_prompt("Question?", _CHUNKS)

    assert "GROUNDING GUARDRAILS" in prompt
    assert "Never write phrases like 'directly addresses'" in prompt
    assert "Do not invent author names" in prompt
