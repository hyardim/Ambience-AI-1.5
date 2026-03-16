"""
Tests that build_grounded_prompt() and build_revision_prompt() correctly inject
uploaded document content into the prompt string when provided.
"""

from src.generation.prompts import (
    _truncate_chunk_text,
    build_grounded_prompt,
    build_revision_prompt,
)

_CHUNKS = [
    {
        "text": "Methotrexate is first-line for RA.",
        "metadata": {"title": "BSR RA Guideline", "source_path": "/data/bsr.pdf"},
        "score": 0.9,
        "page_start": 5,
        "page_end": 5,
    }
]

_FILE_CONTEXT = (
    "[discharge_summary.txt]\n"
    "Patient is a 45F with RRMS. Recent MRI shows 3 new T2 lesions."
)


class TestGroundedPromptFileContext:
    def test_uploaded_documents_block_present(self):
        prompt = build_grounded_prompt("What DMT?", _CHUNKS, file_context=_FILE_CONTEXT)
        assert "UPLOADED DOCUMENTS" in prompt

    def test_file_content_in_prompt(self):
        prompt = build_grounded_prompt("What DMT?", _CHUNKS, file_context=_FILE_CONTEXT)
        assert "3 new T2 lesions" in prompt

    def test_filename_label_in_prompt(self):
        prompt = build_grounded_prompt("What DMT?", _CHUNKS, file_context=_FILE_CONTEXT)
        assert "discharge_summary.txt" in prompt

    def test_no_uploaded_documents_block_when_none(self):
        """File content must not appear in the prompt when file_context is None."""
        prompt = build_grounded_prompt("What DMT?", _CHUNKS, file_context=None)
        assert "3 new T2 lesions" not in prompt
        assert "discharge_summary.txt" not in prompt

    def test_no_uploaded_documents_block_when_empty_string(self):
        """File content must not appear in the prompt when file_context is empty."""
        prompt = build_grounded_prompt("What DMT?", _CHUNKS, file_context="")
        assert "discharge_summary.txt" not in prompt

    def test_uploaded_documents_appears_after_numbered_context(self):
        """Uploaded docs section must come AFTER numbered [1][2]... context."""
        prompt = build_grounded_prompt("What DMT?", _CHUNKS, file_context=_FILE_CONTEXT)
        # The actual file content (not the instruction mention) must be after "Context:"
        assert prompt.index("Context:") < prompt.index("3 new T2 lesions")

    def test_uploaded_documents_appears_before_question(self):
        prompt = build_grounded_prompt("What DMT?", _CHUNKS, file_context=_FILE_CONTEXT)
        assert prompt.index("UPLOADED DOCUMENTS") < prompt.index("Question:")

    def test_citation_hint_present_when_file_context_only(self):
        """Even with no indexed chunks, citation hint should still appear."""
        prompt = build_grounded_prompt(
            "What DMT?", chunks=[], file_context=_FILE_CONTEXT
        )
        assert "citations" in prompt.lower()

    def test_both_patient_context_and_file_context(self):
        prompt = build_grounded_prompt(
            "What DMT?",
            _CHUNKS,
            patient_context={"age": 45, "gender": "female"},
            file_context=_FILE_CONTEXT,
        )
        assert "PATIENT CONTEXT" in prompt
        assert "UPLOADED DOCUMENTS" in prompt
        assert "Age: 45" in prompt
        assert "3 new T2 lesions" in prompt

    def test_evidence_note_is_included_when_provided(self):
        prompt = build_grounded_prompt(
            "What DMT?",
            _CHUNKS,
            evidence_note="Evidence is limited.",
        )
        assert "EVIDENCE NOTE" in prompt
        assert "Evidence is limited." in prompt

    def test_ordering_patient_context_then_context_then_uploaded_docs(self):
        """Section order: PATIENT CONTEXT → Context: → file content → Question:"""
        prompt = build_grounded_prompt(
            "What DMT?",
            _CHUNKS,
            patient_context={"age": 45},
            file_context=_FILE_CONTEXT,
        )
        pc_idx = prompt.index("PATIENT CONTEXT")
        ctx_idx = prompt.index("Context:")
        file_idx = prompt.index("3 new T2 lesions")  # actual file content position
        q_idx = prompt.index("Question:")
        assert pc_idx < ctx_idx < file_idx < q_idx

    def test_patient_context_includes_specialty_severity_and_notes(self):
        prompt = build_grounded_prompt(
            "What DMT?",
            _CHUNKS,
            patient_context={
                "specialty": "neurology",
                "severity": "urgent",
                "notes": "Recent relapse after steroid taper.",
            },
        )

        assert "Specialty: Neurology" in prompt
        assert "Severity: Urgent" in prompt
        assert "Clinical notes: Recent relapse after steroid taper." in prompt

    def test_patient_context_includes_recent_chat_history(self):
        prompt = build_grounded_prompt(
            "What DMT?",
            _CHUNKS,
            patient_context={
                "conversation_history": "User: relapse\nAssistant: review recent MRI",
            },
        )

        assert "RECENT CHAT HISTORY" in prompt
        assert "Assistant: review recent MRI" in prompt


class TestRevisionPromptFileContext:
    def test_file_context_in_revision_prompt(self):
        prompt = build_revision_prompt(
            original_question="What DMT?",
            previous_answer="Interferon beta-1a.",
            specialist_feedback="Consider switching to natalizumab.",
            chunks=_CHUNKS,
            file_context=_FILE_CONTEXT,
        )
        assert "UPLOADED DOCUMENTS" in prompt
        assert "3 new T2 lesions" in prompt

    def test_no_file_context_in_revision_when_none(self):
        prompt = build_revision_prompt(
            original_question="What DMT?",
            previous_answer="Interferon beta-1a.",
            specialist_feedback="Consider switching.",
            chunks=_CHUNKS,
            file_context=None,
        )
        assert "UPLOADED DOCUMENTS" not in prompt

    def test_uploaded_docs_after_context_in_revision(self):
        prompt = build_revision_prompt(
            original_question="What DMT?",
            previous_answer="Interferon.",
            specialist_feedback="Escalate.",
            chunks=_CHUNKS,
            file_context=_FILE_CONTEXT,
        )
        assert prompt.index("Context:") < prompt.index("UPLOADED DOCUMENTS")

    def test_patient_context_is_included_in_revision_prompt(self):
        prompt = build_revision_prompt(
            original_question="What DMT?",
            previous_answer="Interferon.",
            specialist_feedback="Escalate.",
            chunks=_CHUNKS,
            patient_context={"severity": "high", "notes": "Two relapses this year."},
        )

        assert "PATIENT CONTEXT" in prompt
        assert "Severity: High" in prompt
        assert "Clinical notes: Two relapses this year." in prompt

    def test_revision_prompt_includes_evidence_note(self):
        prompt = build_revision_prompt(
            original_question="What DMT?",
            previous_answer="Interferon.",
            specialist_feedback="Escalate.",
            chunks=_CHUNKS,
            evidence_note="Evidence is limited.",
        )

        assert "EVIDENCE NOTE" in prompt
        assert "Evidence is limited." in prompt

    def test_truncate_chunk_text_marks_truncated_content(self):
        text = "A" * 1300

        result = _truncate_chunk_text(text)

        assert result.endswith("…[truncated]")
        assert len(result) <= 1200

    def test_context_formats_page_ranges(self):
        chunks = [
            {
                "text": "Methotrexate is first-line for RA.",
                "metadata": {"title": "BSR RA Guideline"},
                "score": 0.9,
                "page_start": 5,
                "page_end": 6,
            }
        ]

        prompt = build_grounded_prompt("What DMT?", chunks)

        assert "(pages 5-6)" in prompt
