from src.generation import prompts


_DUMMY_CHUNKS = [
    {
        "text": "abcdefghijklmnopqrstuvwxyz",
        "metadata": {"filename": "guideline.pdf"},
        "page_start": 2,
        "page_end": 3,
    }
]


def test_truncate_chunk_text_appends_suffix_and_respects_length():
    truncated = prompts._truncate_chunk_text("abcdefghijklmnopqrstuvwxyz", max_chars=20)
    assert truncated.endswith(" …[truncated]")
    assert len(truncated) <= 20


def test_truncate_chunk_text_returns_original_when_short():
    text = "short"
    assert prompts._truncate_chunk_text(text, max_chars=20) == text


def test_grounded_prompt_no_context_or_files_uses_no_citation_hint():
    prompt = prompts.build_grounded_prompt("Question?", chunks=[], file_context=None)
    assert "Answer (no citations):" in prompt


def test_grounded_prompt_includes_page_notes_and_source_filename():
    prompt = prompts.build_grounded_prompt("Question?", chunks=_DUMMY_CHUNKS)
    assert "Source: guideline.pdf (pages 2-3)" in prompt


def test_format_context_uses_unknown_source_when_missing_metadata():
    context = prompts._format_context([
        {"text": "x", "metadata": {}, "page_start": 1, "page_end": 1}
    ])
    assert "Unknown Source" in context


def test_grounded_prompt_with_file_only_uses_with_citations_hint():
    prompt = prompts.build_grounded_prompt("Question?", chunks=[], file_context="[f]\nbody")
    assert "Answer (with citations):" in prompt


def test_grounded_prompt_orders_sections_with_chunks_and_files():
    prompt = prompts.build_grounded_prompt(
        "Question?",
        chunks=_DUMMY_CHUNKS,
        file_context="[file]\ncontent",
        patient_context={"age": 40},
    )

    patient_index = prompt.index("PATIENT CONTEXT")
    context_index = prompt.index("Context:")
    upload_index = prompt.rindex("UPLOADED DOCUMENTS")
    question_index = prompt.index("Question:")

    assert patient_index < context_index < upload_index < question_index


def test_revision_prompt_no_context_no_files_uses_no_citations_hint():
    prompt = prompts.build_revision_prompt(
        original_question="q",
        previous_answer="a",
        specialist_feedback="f",
        chunks=[],
        file_context=None,
    )
    assert "Revised answer (no citations):" in prompt


def test_revision_prompt_files_only_uses_with_citations_hint_and_order():
    prompt = prompts.build_revision_prompt(
        original_question="q",
        previous_answer="a",
        specialist_feedback="f",
        chunks=[],
        file_context="[file]\ncontent",
    )

    assert "Revised answer (with citations):" in prompt
    assert prompt.index("Context:") < prompt.rindex("UPLOADED DOCUMENTS")
