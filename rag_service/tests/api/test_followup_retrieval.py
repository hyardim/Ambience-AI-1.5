"""
Tests for follow-up query augmentation with conversation history.

Covers:
  - _augment_query_with_history: the function that enriches short follow-up
    queries with the prior GP message before retrieval.
  - GCA emergency rule: the prompt must fire the emergency override when
    jaw claudication + new headache appear in a PMR patient.
"""

import pytest

from src.api.routes import _augment_query_with_history
from src.generation.prompts import build_grounded_prompt

# ---------------------------------------------------------------------------
# _augment_query_with_history
# ---------------------------------------------------------------------------


class TestAugmentQueryWithHistory:
    """Unit tests for the retrieval-query enrichment helper."""

    # ------------------------------------------------------------------
    # Core case — PMR follow-up with GCA symptoms
    # ------------------------------------------------------------------
    def test_jaw_claudication_followup_is_enriched_with_pmr_context(self):
        """The classic GCA follow-up: a short pronoun-led query gains full PMR
        context from the prior GP message so retrieval finds GCA/PMR chunks."""
        ctx = {
            "conversation_history": (
                "GP: 70-year-old with sudden onset bilateral shoulder and hip girdle "
                "pain with morning stiffness >1 hour and raised ESR. Should "
                "polymyalgia rheumatica be started on steroids in primary care?"
            )
        }
        followup = "She also mentions a new headache over the last 3 days and some jaw aching when chewing."
        augmented = _augment_query_with_history(followup, ctx)

        # Prior GP message is prepended
        assert "PMR" in augmented or "polymyalgia" in augmented.lower() or "shoulder" in augmented
        assert "raised ESR" in augmented or "ESR" in augmented
        # Follow-up is still present
        assert "headache" in augmented
        assert "jaw" in augmented
        # Result is longer than the bare follow-up
        assert len(augmented) > len(followup)

    # ------------------------------------------------------------------
    # Only short follow-ups are augmented
    # ------------------------------------------------------------------
    def test_query_with_full_context_is_not_augmented(self):
        """A query that starts with a clinical noun (not a trigger pronoun/word)
        and already contains the full clinical context must not be augmented,
        regardless of whether the conversation history also has context."""
        ctx = {
            "conversation_history": "GP: Patient has type 2 diabetes."
        }
        # Does NOT start with a follow-up trigger word — full standalone query
        standalone_query = (
            "70-year-old female with confirmed PMR on prednisolone 15 mg/day, "
            "now presenting with new onset severe headache, scalp tenderness, and "
            "jaw claudication. Raised CRP 85. What is the appropriate management "
            "of suspected Giant Cell Arteritis in this patient?"
        )
        result = _augment_query_with_history(standalone_query, ctx)
        assert result == standalone_query

    def test_pronoun_led_query_over_300_chars_is_not_augmented(self):
        """A pronoun-led query that is ≥300 chars already contains its own context
        and must not be augmented."""
        ctx = {
            "conversation_history": "GP: Patient has MS."
        }
        # Starts with 'She' but is >300 chars — already self-contained
        query = (
            "She is a 58-year-old with confirmed relapsing-remitting MS on "
            "natalizumab for 4 years, JC antibody index 3.2, now presenting with "
            "left leg weakness and bladder urgency progressing over 48 hours. "
            "MRI shows no new T2 lesions but CSF shows oligoclonal bands. "
            "Should we switch to a different high-efficacy DMT, continue, or "
            "consider plasma exchange? Also, should we check JC virus titre now?"
        )
        assert len(query) >= 300  # pre-condition
        result = _augment_query_with_history(query, ctx)
        assert result == query

    # ------------------------------------------------------------------
    # Only pronoun/continuation-led queries are treated as follow-ups
    # ------------------------------------------------------------------
    def test_query_not_starting_with_followup_trigger_is_unchanged(self):
        """A query that starts with a clinical noun, not a pronoun/continuation
        word, is returned unchanged even if it is short."""
        ctx = {
            "conversation_history": "GP: Patient has rheumatoid arthritis."
        }
        query = "What is the monitoring schedule for methotrexate?"
        result = _augment_query_with_history(query, ctx)
        assert result == query

    def test_she_trigger_is_detected(self):
        """'She' at the start must activate enrichment."""
        ctx = {"conversation_history": "GP: Elderly female with PMR."}
        q = "She now has jaw pain and headache."
        result = _augment_query_with_history(q, ctx)
        assert "PMR" in result

    def test_he_trigger_is_detected(self):
        """'He' at the start must activate enrichment."""
        ctx = {"conversation_history": "GP: Male patient with suspected GCA."}
        q = "He has now developed visual disturbance."
        result = _augment_query_with_history(q, ctx)
        assert "GCA" in result

    def test_the_patient_trigger_is_detected(self):
        """'The patient' at the start must activate enrichment."""
        ctx = {"conversation_history": "GP: Patient on methotrexate for RA."}
        q = "The patient now has a fever and sore throat."
        result = _augment_query_with_history(q, ctx)
        assert "methotrexate" in result

    def test_also_trigger_is_detected(self):
        """'Also' at the start must activate enrichment."""
        ctx = {"conversation_history": "GP: Patient with PMR."}
        q = "Also worth noting she has scalp tenderness."
        result = _augment_query_with_history(q, ctx)
        assert "PMR" in result

    # ------------------------------------------------------------------
    # No history → passthrough
    # ------------------------------------------------------------------
    def test_no_patient_context_returns_query_unchanged(self):
        q = "She also has a headache."
        assert _augment_query_with_history(q, None) == q

    def test_empty_history_returns_query_unchanged(self):
        q = "She also has a headache."
        assert _augment_query_with_history(q, {"age": 70}) == q

    def test_empty_string_history_returns_query_unchanged(self):
        q = "She also has a headache."
        assert _augment_query_with_history(q, {"conversation_history": ""}) == q

    # ------------------------------------------------------------------
    # Length cap — augmented query must not exceed the limit
    # ------------------------------------------------------------------
    def test_augmented_query_does_not_exceed_max_length(self):
        from src.api.routes import _MAX_AUGMENTED_RETRIEVAL_QUERY

        long_history = "GP: " + ("A" * 600)
        ctx = {"conversation_history": long_history}
        q = "She also has headache."
        result = _augment_query_with_history(q, ctx)
        assert len(result) <= _MAX_AUGMENTED_RETRIEVAL_QUERY

    # ------------------------------------------------------------------
    # Multiple GP messages — last one is used as the anchor
    # ------------------------------------------------------------------
    def test_most_recent_gp_message_is_used_as_anchor(self):
        """When there are multiple GP turns, the LAST one provides context."""
        ctx = {
            "conversation_history": (
                "GP: Patient had chest pain last week.\n"
                "GP: 72-year-old with PMR features and raised ESR."
            )
        }
        q = "She now reports jaw pain on chewing."
        result = _augment_query_with_history(q, ctx)
        # Most recent GP message anchors
        assert "PMR" in result or "ESR" in result
        # Follow-up appended
        assert "jaw pain" in result

    # ------------------------------------------------------------------
    # Non-GP history lines are ignored (Specialist: lines)
    # ------------------------------------------------------------------
    def test_specialist_lines_in_history_are_not_used_as_anchor(self):
        ctx = {
            "conversation_history": (
                "GP: Patient with RA on biologic.\n"
                "Specialist: Consider switching to JAK inhibitor."
            )
        }
        q = "She has a new cough."
        result = _augment_query_with_history(q, ctx)
        # GP line used as anchor
        assert "RA" in result or "biologic" in result
        # Specialist text should not be the anchor
        assert "JAK inhibitor" not in result.split("\n")[0]


# ---------------------------------------------------------------------------
# GCA emergency rule in the generation prompt
# ---------------------------------------------------------------------------

_GCA_CHUNKS = [
    {
        "text": (
            "Giant Cell Arteritis (GCA) presents with new-onset headache, "
            "scalp tenderness, and jaw claudication in patients over 50. "
            "BSR guidance: start prednisolone 40–60 mg/day immediately. "
            "Do not wait for temporal artery biopsy before starting treatment. "
            "Biopsy within 2 weeks of starting steroids remains diagnostic. "
            "Visual symptoms (amaurosis fugax, diplopia) require IV methylprednisolone."
        ),
        "metadata": {"title": "BSR: GCA Guideline 2020", "source_name": "BSR"},
        "score": 0.94,
        "page_start": 7,
        "page_end": 8,
    }
]

_PMR_CHUNKS = [
    {
        "text": (
            "PMR presents with bilateral shoulder and pelvic girdle pain, "
            "morning stiffness >45 minutes, and raised ESR/CRP. "
            "First-line: prednisolone 15 mg/day. Response within 1 week is "
            "strongly supportive of the diagnosis."
        ),
        "metadata": {"title": "BSR: PMR Guideline", "source_name": "BSR"},
        "score": 0.90,
        "page_start": 3,
        "page_end": 4,
    }
]


class TestGCAEmergencyRuleInPrompt:
    """Verify the GCA emergency rule is present and correctly formed in the prompt.

    We inspect the prompt string (the one sent to the LLM), not the LLM output.
    The tests verify that the instructions contain the GCA emergency trigger
    and the correct clinical guidance (immediate steroids, no delay).
    """

    def test_gca_emergency_rule_covers_jaw_claudication_trigger(self):
        """The prompt instructions must name jaw claudication as a GCA trigger."""
        ctx = {
            "age": 70,
            "gender": "female",
            "specialty": "rheumatology",
            "conversation_history": (
                "GP: PMR patient, bilateral shoulder pain, raised ESR."
            ),
        }
        prompt = build_grounded_prompt(
            "She also mentions a new headache and jaw aching when chewing.",
            _GCA_CHUNKS + _PMR_CHUNKS,
            patient_context=ctx,
        )
        # Emergency override rule for GCA must be in the instructions part
        instructions_section = prompt[:prompt.index("Context:")]
        assert "jaw claudication" in instructions_section.lower() or \
               "jaw pain on chewing" in instructions_section.lower()

    def test_gca_rule_requires_immediate_steroids_not_wait(self):
        """The instructions must say start steroids immediately — never say
        'may be premature' or 'wait for biopsy'."""
        ctx = {"age": 72, "gender": "female"}
        prompt = build_grounded_prompt(
            "New headache and jaw claudication in PMR patient.",
            _GCA_CHUNKS,
            patient_context=ctx,
        )
        instructions_section = prompt[:prompt.index("Context:")]
        # Must instruct immediate treatment
        assert "immediately" in instructions_section.lower()
        # Must explicitly warn against holding back
        assert "do not" in instructions_section.lower() or "never" in instructions_section.lower()
        # Biopsy timing guidance present
        assert "biopsy" in instructions_section.lower()

    def test_gca_rule_mentions_vision_loss_risk(self):
        """The instructions must mention vision loss to convey the stakes."""
        ctx = {"age": 75}
        prompt = build_grounded_prompt(
            "New onset headache in elderly PMR patient.",
            _GCA_CHUNKS,
            patient_context=ctx,
        )
        instructions_section = prompt[:prompt.index("Context:")]
        assert "vision" in instructions_section.lower()

    def test_gca_rule_is_in_emergency_block_alongside_cauda_equina(self):
        """GCA rule must sit in the same Rule 11 block as cauda equina — both
        are time-critical emergencies with the same 'Immediate action:' prefix."""
        ctx = {"age": 70}
        prompt = build_grounded_prompt(
            "Headache and jaw pain in elderly patient.",
            _GCA_CHUNKS,
            patient_context=ctx,
        )
        instructions_section = prompt[:prompt.index("Context:")]
        # Both emergencies in same rule
        rule11_pos = instructions_section.lower().find("emergencies")
        assert rule11_pos != -1
        rule11_text = instructions_section[rule11_pos:]
        assert "cauda equina" in rule11_text.lower()
        assert "giant cell arteritis" in rule11_text.lower() or "gca" in rule11_text.lower()

    def test_prednisolone_dose_range_present_in_instructions(self):
        """The specific dose range (40–60 mg/day) must be in the instructions
        so the LLM gives actionable guidance even if chunks are missing."""
        ctx = {"age": 71}
        prompt = build_grounded_prompt(
            "Jaw claudication and headache in PMR patient.",
            _GCA_CHUNKS,
            patient_context=ctx,
        )
        instructions_section = prompt[:prompt.index("Context:")]
        assert "40" in instructions_section and "60" in instructions_section

    def test_urgent_referral_instruction_present(self):
        """The instructions must mention urgent referral for GCA."""
        ctx = {"age": 68}
        prompt = build_grounded_prompt(
            "New headache and jaw pain in elderly female with PMR.",
            _GCA_CHUNKS,
            patient_context=ctx,
        )
        instructions_section = prompt[:prompt.index("Context:")]
        assert "referral" in instructions_section.lower()
        assert "rheumatology" in instructions_section.lower()
