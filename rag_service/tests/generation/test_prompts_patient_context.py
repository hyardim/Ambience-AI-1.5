"""
Tests that build_grounded_prompt() and build_revision_prompt() correctly inject
patient context into the prompt string when provided.
"""

import pytest
from src.generation.prompts import build_grounded_prompt, build_revision_prompt


_CHUNKS = [
    {
        "text": "Methotrexate is first-line for RA.",
        "metadata": {"title": "BSR RA Guideline", "source_path": "/data/bsr.pdf"},
        "score": 0.9,
        "page_start": 5,
        "page_end": 5,
    }
]

_FULL_CONTEXT = {
    "age": 45,
    "gender": "female",
    "specialty": "rheumatology",
    "severity": "high",
    "notes": "Type 2 diabetes, eGFR 38",
}


class TestGroundedPromptPatientContext:
    def test_patient_context_block_present(self):
        prompt = build_grounded_prompt(
            "What treatment?", _CHUNKS, patient_context=_FULL_CONTEXT
        )
        assert "PATIENT CONTEXT" in prompt

    def test_age_in_prompt(self):
        prompt = build_grounded_prompt(
            "What treatment?", _CHUNKS, patient_context=_FULL_CONTEXT
        )
        assert "Age: 45" in prompt

    def test_gender_capitalised_in_prompt(self):
        prompt = build_grounded_prompt(
            "What treatment?", _CHUNKS, patient_context=_FULL_CONTEXT
        )
        assert "Gender: Female" in prompt

    def test_specialty_capitalised_in_prompt(self):
        prompt = build_grounded_prompt(
            "What treatment?", _CHUNKS, patient_context=_FULL_CONTEXT
        )
        assert "Specialty: Rheumatology" in prompt

    def test_severity_capitalised_in_prompt(self):
        prompt = build_grounded_prompt(
            "What treatment?", _CHUNKS, patient_context=_FULL_CONTEXT
        )
        assert "Severity: High" in prompt

    def test_clinical_notes_in_prompt(self):
        prompt = build_grounded_prompt(
            "What treatment?", _CHUNKS, patient_context=_FULL_CONTEXT
        )
        assert "eGFR 38" in prompt
        assert "Type 2 diabetes" in prompt

    def test_no_patient_context_block_when_none(self):
        prompt = build_grounded_prompt("What treatment?", _CHUNKS, patient_context=None)
        assert "PATIENT CONTEXT" not in prompt

    def test_no_patient_context_block_when_empty_dict(self):
        prompt = build_grounded_prompt("What treatment?", _CHUNKS, patient_context={})
        assert "PATIENT CONTEXT" not in prompt

    def test_partial_context_age_only(self):
        prompt = build_grounded_prompt(
            "What treatment?", _CHUNKS, patient_context={"age": 72}
        )
        assert "PATIENT CONTEXT" in prompt
        assert "Age: 72" in prompt
        assert "Gender" not in prompt
        assert "Clinical notes" not in prompt

    def test_patient_context_appears_before_question(self):
        prompt = build_grounded_prompt(
            "What treatment?", _CHUNKS, patient_context=_FULL_CONTEXT
        )
        assert prompt.index("PATIENT CONTEXT") < prompt.index("Question:")

    def test_patient_context_appears_before_numbered_context(self):
        prompt = build_grounded_prompt(
            "What treatment?", _CHUNKS, patient_context=_FULL_CONTEXT
        )
        assert prompt.index("PATIENT CONTEXT") < prompt.index("Context:")


class TestRevisionPromptPatientContext:
    def test_patient_context_block_in_revision_prompt(self):
        prompt = build_revision_prompt(
            original_question="What treatment?",
            previous_answer="Methotrexate.",
            specialist_feedback="Consider renal function.",
            chunks=_CHUNKS,
            patient_context=_FULL_CONTEXT,
        )
        assert "PATIENT CONTEXT" in prompt
        assert "Age: 45" in prompt
        assert "eGFR 38" in prompt

    def test_no_patient_context_in_revision_when_none(self):
        prompt = build_revision_prompt(
            original_question="What treatment?",
            previous_answer="Methotrexate.",
            specialist_feedback="Consider renal function.",
            chunks=_CHUNKS,
            patient_context=None,
        )
        assert "PATIENT CONTEXT" not in prompt
