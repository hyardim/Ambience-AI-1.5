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


def test_select_answer_mode_does_not_treat_urgent_severity_as_emergency_alone() -> None:
    mode = select_answer_mode(
        "65-year-old with rapidly progressive gait disturbance and urinary "
        "incontinence over 3 months. CT head shows ventriculomegaly. "
        "Should normal pressure hydrocephalus be suspected and how urgently "
        "should this be referred?",
        severity="urgent",
    )

    assert mode == "strict_guideline"


def test_select_answer_mode_treats_emergency_severity_as_emergency() -> None:
    mode = select_answer_mode(
        "Assess new severe back pain with neurological symptoms.",
        severity="emergency",
    )

    assert mode == "emergency"


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


def test_grounded_prompt_includes_routine_low_risk_mode_instructions() -> None:
    prompt = build_grounded_prompt(
        "What is the best OTC painkiller for mild headache?",
        _CHUNKS,
        answer_mode="routine_low_risk",
    )

    assert "ROUTINE LOW-RISK MODE" in prompt
    assert "ANSWER MODE\nroutine_low_risk" in prompt


def test_grounded_prompt_falls_back_to_strict_for_invalid_mode() -> None:
    prompt = build_grounded_prompt(
        "Question about something?",
        _CHUNKS,
        answer_mode="nonexistent_mode",
    )

    assert "STRICT GUIDELINE MODE" in prompt
    assert "ANSWER MODE\nstrict_guideline" in prompt


def test_revision_prompt_falls_back_to_strict_for_invalid_mode() -> None:
    from src.generation.prompts import build_revision_prompt

    prompt = build_revision_prompt(
        original_question="What about X?",
        previous_answer="Some answer.",
        specialist_feedback="Add more detail.",
        chunks=_CHUNKS,
        answer_mode="bogus_mode",
    )

    assert "STRICT GUIDELINE MODE" in prompt
    assert "ANSWER MODE\nstrict_guideline" in prompt


def test_matching_signals_high_token_overlap() -> None:
    from src.generation.prompts import _matching_signals

    # Use words that overlap as individual tokens but NOT as bigram phrases.
    # Scatter overlapping words among non-overlapping ones so adjacent pairs differ.
    chunk = {
        "text": (
            "alpha migraine beta treatment gamma prevention delta acute"
        ),
        "metadata": {"title": "Short"},
    }

    result = _matching_signals(
        "migraine treatment prevention acute",
        chunk,
    )

    assert "high token overlap" in result


def test_matching_signals_title_close_match() -> None:
    from src.generation.prompts import _matching_signals

    chunk = {
        "text": "Some text about treatment.",
        "metadata": {"title": "Migraine treatment guidance overview"},
    }

    result = _matching_signals("migraine treatment guidance", chunk)

    assert "title closely matches" in result


def test_matching_signals_section_close_match() -> None:
    from src.generation.prompts import _matching_signals

    chunk = {
        "text": "Some unrelated text.",
        "metadata": {"title": "Guide"},
        "section_path": "Migraine treatment acute therapy",
    }

    result = _matching_signals("migraine treatment acute therapy", chunk)

    assert "section heading closely matches" in result
