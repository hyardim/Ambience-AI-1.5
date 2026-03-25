import re

from ..config import generation_config

MAX_CHARS_PER_CHUNK = 1200
_MAX_INPUT_LENGTH = 10_000

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
# NOTE: ACTIVE_PROMPT is resolved **once at import time** from
# ``generation_config.prompt_variant``.  This is intentional -- reading the
# config on every call would add overhead for a value that should not change
# at runtime.  **A process restart is required** to pick up a new variant.
ACTIVE_PROMPT = (
    generation_config.prompt_variant
    if generation_config.prompt_variant in PROMPT_VARIANTS
    else "new"
)

# ---------------------------------------------------------------------------
# Variant A — original: strict, context-only, refuses when no sources found
# ---------------------------------------------------------------------------
_INSTRUCTIONS_ORIGINAL = (
    "You are a cautious clinical assistant. Use only the provided context to "
    "answer the clinician's question. "
    "Cite supporting passages with the bracket numbers given in the Context section "
    "(e.g., [1], [2]) and only cite passages you actually use. "
    "Do NOT use bracket numbers for uploaded documents — cite them as "
    "'Uploaded document' instead. "
    "If there is no relevant context or the question appears non-medical/off-topic "
    "(e.g., small talk), politely state that you cannot provide clinical guidance "
    "without relevant medical context. "
    "Do not fabricate context or cite sources when none are available. "
    "Keep the response concise and factual."
)

# ---------------------------------------------------------------------------
# Variant B — balanced: health LLM with honest sourcing
# ---------------------------------------------------------------------------
_INSTRUCTIONS_NEW = (
    "You are a clinical decision-support assistant for a GP. "
    "The indexed guideline passages below are your PRIMARY and most "
    "authoritative source.\n\n"
    "Rules for answering:\n"
    "1. INDEXED CITATIONS FIRST: Base your answer on the indexed passages only. "
    "Cite them with [1], [2] etc. only when a passage directly supports the "
    "specific claim you are making. "
    "Read each passage carefully — if it covers a different condition or topic "
    "than the question, "
    "do not cite it, even if it contains a related keyword.\n"
    "2. UPLOADED DOCUMENTS: If an 'UPLOADED DOCUMENTS' section is present, it "
    "contains patient-specific files (e.g. a guideline PDF or clinical "
    "document). Use this content to answer the question. "
    "Cite it as 'Uploaded document' — do NOT use bracket numbers for it.\n"
    "3. HONEST SCOPE: If the indexed passages do not cover the question's "
    "topic, say so clearly in one sentence and do not add uncited clinical "
    "advice.\n"
    "4. NO FABRICATION: Do not invent drug doses, statistics, guideline codes, "
    "study references, "
    "author names, or year references — not even for well-known studies. "
    "If you are uncertain, say so explicitly.\n"
    "5. CONFLICTING SOURCES: If an uploaded document contradicts an indexed "
    "guideline passage, flag the discrepancy explicitly (e.g. 'Note: the "
    "uploaded document states X, whereas the indexed "
    "guideline states Y').\n\n"
    "Response format:\n"
    "Write a structured answer that includes only claims supported by indexed "
    "passages and/or uploaded documents. "
    "When evidence is available, prefer 4-8 short sentences rather than a "
    "single-line response. "
    "If the user asks multiple parts (for example investigations, imaging, and "
    "referral pathway), answer each part explicitly in separate sentences. "
    "For each recommended test or imaging item, add a brief rationale sentence "
    "about what it helps assess, but only when that rationale is explicitly "
    "supported by citations. "
    "If the clinician asks what a finding could mean, provide interpretation "
    "only when directly supported by cited passages; otherwise state that the "
    "interpretation detail is not directly covered by indexed passages. "
    "If only some parts are covered, answer the covered parts and state which "
    "part is not directly addressed by indexed passages. "
    "Every clinical claim sentence must include a valid indexed citation [N] "
    "or explicitly cite 'Uploaded document'. "
    "Do not include treatment or management recommendations unless the question "
    "explicitly asks for treatment or management. "
    "Do not include uncited safety advice, monitoring advice, or treatment "
    "advice. "
    "Do not include section labels or lead-ins such as 'General clinical "
    "context', 'Safety considerations', or 'Regarding safety considerations'. "
    "Do not use guideline subsection references as citations (for example "
    "[1.4.4]) and do not add 'Source:' lines."
)


def _active_instructions() -> str:
    return _INSTRUCTIONS_NEW if ACTIVE_PROMPT == "new" else _INSTRUCTIONS_ORIGINAL


def _format_context(chunks: list[dict]) -> str:
    """Render retrieved chunks for the prompt. Empty string when none."""
    if not chunks:
        return ""

    lines = []
    for idx, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata", {}) or {}
        source = (
            metadata.get("title")
            or metadata.get("source_name")
            or metadata.get("filename")
            or "Unknown Source"
        )
        page_start = chunk.get("page_start")
        page_end = chunk.get("page_end")
        page_note = ""
        if page_start is not None and page_end is not None:
            if page_start == page_end:
                page_note = f" (page {page_start})"
            else:
                page_note = f" (pages {page_start}-{page_end})"

        lines.append(
            f"[{idx}] {_truncate_chunk_text(chunk.get('text', ''))}\n"
            f"Source: {source}{page_note}"
        )

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
        gender = _sanitize_input(
            patient_context["gender"], max_length=50
        ).capitalize()
        parts.append(f"Gender: {gender}")
    if patient_context.get("specialty"):
        spec = _sanitize_input(
            patient_context["specialty"], max_length=100
        ).capitalize()
        parts.append(f"Specialty: {spec}")
    if patient_context.get("severity"):
        sev = _sanitize_input(
            patient_context["severity"], max_length=50
        ).capitalize()
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
) -> str:
    """Build the main RAG prompt from a question, chunks, and context.

    All user-supplied text (question, patient_context values, file_context) is
    sanitized to strip injection patterns and control characters before being
    inserted into the prompt.
    """
    question = _sanitize_input(question)
    if file_context:
        file_context = _sanitize_input(file_context, max_length=_MAX_INPUT_LENGTH * 2)

    context_block = _format_context(chunks)
    has_context = bool(chunks)
    has_files = bool(file_context)

    patient_block = _format_patient_context(patient_context)
    # Numbered context comes first so [1][2]... anchor to indexed passages only.
    context_section = "Context:\n" + (context_block if has_context else "(none)")
    citation_hint = (
        "Answer (with citations):"
        if (has_context or has_files)
        else "Answer (no citations):"
    )

    parts = [_active_instructions()]
    if patient_block:
        parts.append(patient_block)
    if evidence_note:
        parts.append(f"EVIDENCE NOTE\n{evidence_note}")
    parts.append(context_section)
    # Uploaded documents come after numbered context and are not cited as [N].
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
) -> str:
    """Revise a previous answer based on specialist feedback, grounded in context.

    User-supplied strings are sanitized before prompt assembly.
    """
    original_question = _sanitize_input(original_question)
    specialist_feedback = _sanitize_input(specialist_feedback)
    if file_context:
        file_context = _sanitize_input(file_context, max_length=_MAX_INPUT_LENGTH * 2)
    context_block = _format_context(chunks)
    has_context = bool(chunks)

    # Use the same active prompt variant as the initial generation so
    # citation and sourcing rules stay consistent across revisions.
    base_instructions = _active_instructions()
    instructions = (
        f"{base_instructions}\n\n"
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
    if evidence_note:
        parts.append(f"EVIDENCE NOTE\n{evidence_note}")
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
