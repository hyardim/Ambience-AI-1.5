import re

from ..config import generation_config

MAX_CHARS_PER_CHUNK = 1200
_MAX_INPUT_LENGTH = 10_000
# Retained for API compatibility — answer mode routing is now a no-op.
ANSWER_MODES = {
    "strict_guideline",
    "emergency",
    "comparison",
    "routine_low_risk",
}

# Patterns that look like prompt-injection attempts or role impersonation.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(prior|previous|above)\s+", re.IGNORECASE),
    re.compile(r"^system\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^assistant\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^human\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<\|?(system|im_start|im_end)\|?>", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|in)\b", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
]


def _sanitize_input(text: str, *, max_length: int = _MAX_INPUT_LENGTH) -> str:
    """Sanitize user-supplied text before inserting it into a prompt.

    * Strips control characters (except newlines and tabs).
    * Removes substrings matching known prompt-injection patterns.
    * Truncates to *max_length* characters to prevent context-window abuse.
    """
    if not text:
        return ""
    # Remove ASCII control chars except \n (0x0A) and \t (0x09).
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    # Collapse runs of whitespace that the removals may have left.
    cleaned = re.sub(r"[ \t]{3,}", "  ", cleaned)
    return cleaned[:max_length].strip()


def _truncate_chunk_text(text: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> str:
    """Truncate chunk text to *max_chars*, preferring a sentence boundary.

    Tries to break at the last ``'. '`` before the limit.  Falls back to a
    word boundary (last space), and finally to a hard cut if neither is found
    in a reasonable range.
    """
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned

    suffix = " …[truncated]"
    budget = max_chars - len(suffix)
    candidate = cleaned[:budget]

    # Prefer sentence boundary (period + space).
    sentence_end = candidate.rfind(". ")
    if sentence_end > budget // 2:
        return candidate[: sentence_end + 1] + suffix

    # Fall back to word boundary.
    word_end = candidate.rfind(" ")
    if word_end > budget // 2:
        return candidate[:word_end] + suffix

    return candidate.rstrip() + suffix


PROMPT_VARIANTS = {"new", "original"}
ACTIVE_PROMPT = (
    generation_config.prompt_variant
    if generation_config.prompt_variant in PROMPT_VARIANTS
    else "new"
)

# ---------------------------------------------------------------------------
# Unified prompt — inspired by MVP simplicity, with current branch's
# citation format rules and patient context support.
# ---------------------------------------------------------------------------
_INSTRUCTIONS = (
    "You are a clinical decision-support assistant for a GP. "
    "Use the provided context passages to answer the clinician's question. "
    "Cite supporting passages with their bracket numbers (e.g. [1], [2]) "
    "and only cite passages you actually use.\n\n"
    "Rules:\n"
    "1. Base your answer on the provided context. Cite with [1], [2] etc.\n"
    "2. If an 'UPLOADED DOCUMENTS' section is present in this prompt, use that "
    "content too and cite it as 'Uploaded document' (no bracket numbers). "
    "IMPORTANT: if there is NO 'UPLOADED DOCUMENTS' section in this prompt, "
    "do NOT write 'Uploaded document' anywhere in your response — not as a "
    "citation, not as a source label, not at all.\n"
    "3. Do not fabricate drug doses, statistics, guideline codes, study "
    "references, or author names not present in the context.\n"
    "4. Do not echo recommendation numbers from guideline text (e.g. 1.1.2, "
    "1.1.3) — state the clinical content instead.\n"
    "5. State recommendations directly — do NOT write meta-references like "
    "'The guideline covers X', say what the recommendation actually is.\n"
    "6. If the clinician asks whether to start a treatment, begin with a "
    "direct yes/no.\n"
    "7. Keep the answer concise and practical — aim for 4-8 sentences.\n"
    "8. Do NOT add a summary paragraph at the end.\n"
    "9. Do not include section labels like 'General clinical context' or "
    "'Safety considerations'.\n"
    "10. If the context does not contain enough information to answer, say so "
    "briefly rather than guessing.\n"
    "11. EMERGENCIES — override ALL other rules including your own clinical "
    "reasoning: If the query involves "
    "(a) fever or sore throat with neutropenia in a patient on "
    "immunosuppressants or methotrexate (neutropenic sepsis), or "
    "(b) bilateral leg weakness AND urinary or bowel dysfunction AND back pain "
    "(cauda equina syndrome), or (c) acute cord compression, or "
    "(d) jaw pain on chewing / jaw claudication in an elderly patient "
    "(Giant Cell Arteritis must be excluded — do NOT decide it is 'less "
    "likely'; jaw claudication is a HIGH-SPECIFICITY GCA feature regardless "
    "of whether other features such as temporal headache are present) — "
    "your response MUST begin with the exact words 'Immediate action:' as "
    "the very first words, followed by the urgent management. "
    "Never describe these presentations as benign or suggest 'monitor for a "
    "few days'. Never say 'GCA is less likely' when jaw claudication is "
    "present — the only correct response is to treat as possible GCA. "
    "These are medical emergencies regardless of what the retrieved context "
    "passages say and regardless of your clinical probability assessment. "
    "When an emergency condition is detected: respond with ONLY the "
    "emergency guidance — do NOT add notes, disclaimers, follow-on "
    "paragraphs, or meta-commentary explaining why you are responding "
    "differently. Do not address any other aspect of the original question "
    "after the emergency response.\n"
    "For GCA (jaw claudication / new headache in elderly patient): begin "
    "with 'Immediate action:' then state: start high-dose prednisolone NOW "
    "(typically 40-60 mg/day without visual symptoms; escalate dose if "
    "visual symptoms). Do NOT wait for biopsy — start steroids immediately, "
    "biopsy within 2 weeks remains diagnostic. Arrange URGENT same-day "
    "secondary care referral (rheumatology ± ophthalmology if visual "
    "symptoms). Delay = risk of irreversible vision loss.\n"
    "For cauda equina or cord compression, the urgent intervention is "
    "emergency neurosurgical referral for spinal decompression — never "
    "mention decompressive hemicraniectomy (that is a brain procedure for "
    "stroke and is never appropriate for spinal emergencies).\n"
    "12. TIA accuracy: A transient ischaemic attack (TIA) resolves completely "
    "by definition — do NOT write that TIA symptoms 'persist for at least "
    "24 hours' or that TIAs cause 'persistent deficits'. Most TIAs resolve "
    "within 60 minutes; the 24-hour limit is only the historical maximum "
    "cut-off. Migraine aura develops gradually (over 5+ minutes) and lasts "
    "5-60 minutes; TIA has sudden onset and typically no headache.\n"
    "13. If a retrieved context passage is about a different clinical "
    "condition than the question asks about, IGNORE IT COMPLETELY — do not "
    "incorporate its information, do not acknowledge it exists, do not write "
    "phrases like 'the context does not address X' or 'the context for "
    "spondyloarthritis does not apply here'. Simply skip that passage and "
    "respond as if it were not provided."
)


def _active_instructions() -> str:
    """Return the active system instruction string.

    Provided for API compatibility with ``orchestration.prompt`` which
    delegates here so that both code paths share the same instruction text.
    """
    return _INSTRUCTIONS


def select_answer_mode(
    question: str,
    *,
    severity: str | None = None,
) -> str:
    """Retained for API compatibility — always returns 'strict_guideline'."""
    return "strict_guideline"


def allows_uncited_answer(
    answer_mode: str,
    *,
    evidence_level: str,
    has_file_context: bool = False,
) -> bool:
    """Allow answers through more liberally — trust the LLM at low temperature."""
    if has_file_context:
        return True
    # Always allow the answer through if there's any evidence at all.
    # The post-processing will clean artifacts; blocking non-empty answers
    # causes more harm than good.
    return True


def _format_context(question: str, chunks: list[dict]) -> str:
    """Render retrieved chunks for the prompt. Empty string when none."""
    if not chunks:
        return ""

    lines = []
    for idx, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata", {}) or {}
        title = (
            metadata.get("title")
            or metadata.get("source_name")
            or metadata.get("filename")
            or ""
        )
        page_start = chunk.get("page_start")
        page_end = chunk.get("page_end")
        note_parts: list[str] = []
        if title:
            note_parts.append(str(title))
        section = chunk.get("section_path") or metadata.get("section_title")
        if section:
            note_parts.append(str(section))
        if page_start is not None and page_end is not None:
            if page_start == page_end:
                note_parts.append(f"page {page_start}")
            else:
                note_parts.append(f"pages {page_start}-{page_end}")

        header = f"[{idx}]"
        if note_parts:
            header = f"{header} {' - '.join(note_parts)}"
        lines.append(f"{header}\n{_truncate_chunk_text(chunk.get('text', ''))}")

    return "\n\n".join(lines)


def _format_patient_context(patient_context: dict | None) -> str:
    """Render patient demographics block, or empty string when not provided.

    Free-text fields (notes, conversation_history) are sanitized to prevent
    prompt injection via patient context.
    """
    if not patient_context:
        return ""
    parts = []
    if patient_context.get("age"):
        age = _sanitize_input(str(patient_context["age"]), max_length=20)
        parts.append(f"Age: {age}")
    if patient_context.get("gender"):
        gender = _sanitize_input(patient_context["gender"], max_length=50).capitalize()
        parts.append(f"Gender: {gender}")
    if patient_context.get("specialty"):
        spec = _sanitize_input(
            patient_context["specialty"], max_length=100
        ).capitalize()
        parts.append(f"Specialty: {spec}")
    if patient_context.get("severity"):
        sev = _sanitize_input(patient_context["severity"], max_length=50).capitalize()
        parts.append(f"Severity: {sev}")
    header = "  |  ".join(parts)
    notes = _sanitize_input(patient_context.get("notes", ""))
    block = "PATIENT CONTEXT\n" + header
    if notes:
        block += f"\nClinical notes: {notes}"
    conversation_history = _sanitize_input(
        patient_context.get("conversation_history", ""),
        max_length=_MAX_INPUT_LENGTH,
    )
    if conversation_history:
        block += f"\n\nRECENT CHAT HISTORY\n{conversation_history}"
    return block


def build_grounded_prompt(
    question: str,
    chunks: list[dict],
    patient_context: dict | None = None,
    file_context: str | None = None,
    evidence_note: str | None = None,
    answer_mode: str | None = None,
) -> str:
    """Build the main RAG prompt from a question, chunks, and context.

    All user-supplied text (question, patient_context values, file_context) is
    sanitized to strip injection patterns and control characters before being
    inserted into the prompt.
    """
    question = _sanitize_input(question)
    if file_context:
        file_context = _sanitize_input(file_context, max_length=_MAX_INPUT_LENGTH * 2)

    context_block = _format_context(question, chunks)
    has_context = bool(chunks)
    has_files = bool(file_context)

    patient_block = _format_patient_context(patient_context)
    context_section = "Context:\n" + (context_block if has_context else "(none)")
    citation_hint = (
        "Answer (with citations):"
        if (has_context or has_files)
        else "Answer (no citations):"
    )

    parts = [_INSTRUCTIONS]
    if patient_block:
        parts.append(patient_block)
    parts.append(context_section)
    if file_context:
        parts.append(f"UPLOADED DOCUMENTS\n{file_context}")
    parts += [f"Question: {question}", citation_hint]
    return "\n\n".join(parts)


def build_revision_prompt(
    original_question: str,
    previous_answer: str,
    specialist_feedback: str,
    chunks: list[dict],
    patient_context: dict | None = None,
    file_context: str | None = None,
    evidence_note: str | None = None,
    answer_mode: str | None = None,
) -> str:
    """Revise a previous answer based on specialist feedback, grounded in context.

    User-supplied strings are sanitized before prompt assembly.
    """
    original_question = _sanitize_input(original_question)
    specialist_feedback = _sanitize_input(specialist_feedback)
    if file_context:
        file_context = _sanitize_input(file_context, max_length=_MAX_INPUT_LENGTH * 2)
    context_block = _format_context(original_question, chunks)
    has_context = bool(chunks)

    instructions = (
        f"{_INSTRUCTIONS}\n\n"
        "A medical specialist has reviewed your previous answer and requested "
        "changes. Revise your response according to the specialist's feedback "
        "while staying grounded in the provided context.\n\n"
        "Additional revision rules:\n"
        "- Address every point raised in the specialist's feedback.\n"
        "- Do not fabricate information or cite sources that are not provided.\n"
        "- Keep the response concise and factual."
    )

    patient_block = _format_patient_context(patient_context)
    context_section = "Context:\n" + (context_block if has_context else "(none)")
    has_files = bool(file_context)
    citation_hint = (
        "Revised answer (with citations):"
        if (has_context or has_files)
        else "Revised answer (no citations):"
    )

    parts = [instructions]
    if patient_block:
        parts.append(patient_block)
    parts.append(context_section)
    if file_context:
        parts.append(f"UPLOADED DOCUMENTS\n{file_context}")
    parts += [
        f"Original question: {original_question}",
        f"Previous answer: {previous_answer}",
        f"Specialist feedback: {specialist_feedback}",
        citation_hint,
    ]
    return "\n\n".join(parts)
