import re

from ..config import generation_config
from ..retrieval.relevance import phrase_overlap_count, query_overlap_count

MAX_CHARS_PER_CHUNK = 1200
_MAX_INPUT_LENGTH = 10_000
ANSWER_MODES = {
    "strict_guideline",
    "emergency",
    "comparison",
    "routine_low_risk",
}

_COMPARISON_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(distinguish\w*|differentiat\w*|compare|comparison)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bvs\b", re.IGNORECASE),
    re.compile(r"\bversus\b", re.IGNORECASE),
)
_EMERGENCY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(cauda equina|cord compression|spinal emergency|neutropenic sepsis)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(urinary retention|saddle anaesthesia|bilateral leg weakness)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(neutropenia|low neutrophils)\b.*\b(fever|sore throat|pyrexia)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(fever|sore throat|pyrexia)\b.*\b(neutropenia|low neutrophils)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(immediate action|before transfer|same-day|urgent transfer)\b",
        re.IGNORECASE,
    ),
)
_LOW_RISK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\btremor\b", re.IGNORECASE),
    re.compile(r"\bcaffeine\b", re.IGNORECASE),
    re.compile(r"\banxiety\b", re.IGNORECASE),
    re.compile(r"\bno (rigidity|bradykinesia|neurological deficit)\b", re.IGNORECASE),
)
_WORKUP_QUERY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(before|prior to) referral\b", re.IGNORECASE),
    re.compile(r"\bbaseline (blood )?tests?\b", re.IGNORECASE),
    re.compile(r"\bimaging\b", re.IGNORECASE),
    re.compile(r"\bwork[- ]?up\b", re.IGNORECASE),
)

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
    "authoritative source. "
    "Your general clinical knowledge plays a SUPPLEMENTARY role only — use it "
    "to explain terminology, provide clinical context, or bridge small gaps in "
    "the indexed evidence, never to replace it.\n\n"
    "Rules for answering:\n"
    "0. RELEVANCE DISCIPLINE: The context items are already ordered by estimated "
    "direct relevance, with [1] the strongest match. Prefer the lowest-numbered "
    "passage that directly addresses the clinical point. Do not cite a higher-"
    "numbered passage if a lower-numbered passage answers the same point more "
    "specifically.\n"
    "1. INDEXED CITATIONS FIRST: Base your answer on the indexed passages. "
    "Cite them with [1], [2] etc. only when a passage directly supports the "
    "specific claim you are making. "
    "Read each passage carefully — if it covers a different condition or topic "
    "than the question, a different complication, or a different referral pathway, "
    "do not cite it, even if it contains a related keyword.\n"
    "2. UPLOADED DOCUMENTS: If an 'UPLOADED DOCUMENTS' section is present, it "
    "contains patient-specific files (e.g. a guideline PDF or clinical "
    "document). Use this content to answer the question. "
    "Cite it as 'Uploaded document' — do NOT use bracket numbers for it.\n"
    "3. SUPPLEMENTARY KNOWLEDGE: You may use general clinical knowledge to fill "
    "gaps the indexed passages do not address. Keep this clearly separate — "
    "never mix it with cited content or "
    "attach citation numbers to it.\n"
    "4. HONEST SCOPE: If the indexed passages do not cover the question's "
    "topic, say so in one sentence. If the question is non-medical, off-topic, "
    "or unrelated to patient care, STOP there and do not add a 'General clinical "
    "context:' section. Only use 'General clinical context:' for clearly medical "
    "questions that are partially but not fully covered by the indexed evidence.\n"
    "5. NO FABRICATION: Do not invent drug doses, statistics, guideline codes, "
    "study references, "
    "author names, or year references — not even for well-known studies. "
    "If you are uncertain, say so explicitly.\n"
    "6. CONFLICTING SOURCES: If an uploaded document contradicts an indexed "
    "guideline passage, flag the discrepancy explicitly (e.g. 'Note: the "
    "uploaded document states X, whereas the indexed "
    "guideline states Y').\n\n"
    "Response format:\n"
    "First, write only statements that are directly supported by the indexed "
    "passages, each cited with [N]. "
    "Do NOT include any statistic, percentage, risk factor, or clinical claim "
    "in this section unless it appears in an indexed passage and you are "
    "citing it. If a claim is not in an indexed passage, it "
    "does not belong here — move it to the general block below.\n"
    "Then, if there is additional useful context from general medical "
    "knowledge, add a single paragraph starting with exactly: 'General clinical "
    "context:' — no citation numbers, no statistics, no author names. "
    "If the indexed evidence fully covers the question, or if the question is "
    "non-medical/off-topic, omit this block entirely.\n"
    "If safety considerations apply to this question, end with one or two "
    "sentences on relevant safety flags or monitoring. "
    "If there are no safety implications, omit this section entirely."
)


_EMERGENCY_BASE_INSTRUCTIONS = (
    "You are a clinical decision-support assistant for a GP handling an urgent "
    "question. Use the indexed passages as the primary evidence. Give the safest "
    "concrete immediate action first, then a brief explanation. Cite only claims "
    "that are directly supported by the indexed passages. If the passages support "
    "the emergency pattern but not every operational detail, say 'Based on standard "
    "emergency clinical practice:' before any uncited bridging sentence."
)

_COMPARISON_BASE_INSTRUCTIONS = (
    "You are a clinical decision-support assistant for a GP answering a comparison "
    "question. Use the indexed passages as the primary evidence. Compare the two "
    "conditions named in the question directly, using concrete distinguishing "
    "features supported by the passages. Do not drift into a one-sided workflow "
    "answer for only one condition."
)


def _active_instructions(answer_mode: str | None = None) -> str:
    if ACTIVE_PROMPT == "original":
        return _INSTRUCTIONS_ORIGINAL
    if answer_mode == "emergency":
        return _EMERGENCY_BASE_INSTRUCTIONS
    if answer_mode == "comparison":
        return _COMPARISON_BASE_INSTRUCTIONS
    return _INSTRUCTIONS_NEW


def select_answer_mode(
    question: str,
    *,
    severity: str | None = None,
) -> str:
    question_lc = question.lower()
    severity_lc = (severity or "").strip().lower()

    if severity_lc == "emergency" or any(
        pattern.search(question) for pattern in _EMERGENCY_PATTERNS
    ):
        return "emergency"

    if any(pattern.search(question) for pattern in _COMPARISON_PATTERNS):
        return "comparison"

    low_risk_hits = sum(1 for pattern in _LOW_RISK_PATTERNS if pattern.search(question))
    if low_risk_hits >= 2:
        return "routine_low_risk"

    if (
        (
            "initial management" in question_lc
            or "before referral" in question_lc
            or "prior to referral" in question_lc
            or "baseline blood tests" in question_lc
            or "baseline tests" in question_lc
            or "what baseline" in question_lc
        )
        and any(
            marker in question_lc
            for marker in (
                "no neurological deficit",
                "no persistent deficit",
                "no clear diagnosis",
                "mildly raised",
                "intermittent",
                "worse with anxiety",
                "worse with caffeine",
                "over 4 months",
            )
        )
    ):
        return "routine_low_risk"

    return "strict_guideline"


def allows_uncited_answer(
    answer_mode: str,
    *,
    evidence_level: str,
    has_file_context: bool = False,
) -> bool:
    if has_file_context:
        return True
    if answer_mode == "routine_low_risk":
        return True
    return answer_mode == "comparison" and evidence_level == "weak"


def _mode_instructions(answer_mode: str) -> str:
    if answer_mode == "emergency":
        return (
            "EMERGENCY MODE:\n"
            "- Start with exactly 'Immediate action:' and give the urgent step "
            "in the first sentence.\n"
            "- The first sentence must contain the concrete action itself (for "
            "example stop a drug, admit, refer same-day, transfer urgently, "
            "or arrange immediate assessment). Do not write only that action "
            "is required.\n"
            "- Use decisive wording for emergency transfer or same-day "
            "escalation when supported.\n"
            "- Keep the answer short and operational. Do not add a 'General "
            "clinical context:' block unless essential.\n"
            "- If the indexed passages support only the red-flag pattern but "
            "not every operational detail, say 'Based on standard emergency "
            "clinical practice:' for the uncited part.\n"
            "- Never bury the immediate action inside explanation.\n"
            "- If you cannot name a concrete urgent action from the indexed "
            "passages, say the evidence supports urgent same-day specialist or "
            "hospital assessment and then state the safest immediate step."
        )
    if answer_mode == "comparison":
        return (
            "COMPARISON MODE:\n"
            "- Start with exactly 'Answer:' and directly answer the comparison "
            "question.\n"
            "- Then add a section starting exactly 'Key differences:' with "
            "short feature-based bullet points.\n"
            "- You must address both sides of the comparison explicitly. Do "
            "not answer with guidance for only one condition.\n"
            "- Compare onset, symptom type, progression, duration, and "
            "follow-up/referral when relevant.\n"
            "- For each condition named in the question, give at least one "
            "distinctive feature if the indexed evidence supports it.\n"
            "- Avoid vague filler like 'consider history' or 'clinical "
            "judgement' unless followed by a concrete distinguishing feature.\n"
            "- If uncertainty remains, end with one clear safety/referral sentence.\n"
            "- Do not turn a comparison answer into a one-sided imaging or "
            "referral workflow unless the question specifically asks for that."
        )
    if answer_mode == "routine_low_risk":
        return (
            "ROUTINE LOW-RISK MODE:\n"
            "- If the indexed passages are only indirectly relevant, do NOT "
            "refuse solely for lack of a perfect guideline match.\n"
            "- Provide a practical answer based on standard clinical practice "
            "when the scenario is common and low risk.\n"
            "- If you use standard clinical practice rather than a directly "
            "answering indexed passage, write one sentence starting exactly "
            "'Based on standard clinical practice:' and do not attach bracket "
            "citations to that sentence.\n"
            "- Keep the answer concise, useful, and safety-net focused."
        )
    return (
        "STRICT GUIDELINE MODE:\n"
        "- Stay close to the indexed evidence.\n"
        "- If the indexed evidence is insufficient for an important claim, say "
        "so explicitly.\n"
        "- Do not fill large gaps with uncited medical knowledge."
    )


def _grounding_guardrails() -> str:
    return (
        "GROUNDING GUARDRAILS:\n"
        "- Never write phrases like 'directly addresses', 'the guideline "
        "recommends', or 'the passage states' unless the indexed passage "
        "explicitly supports that exact claim.\n"
        "- Keep grounded statements and general clinical context clearly separate.\n"
        "- Do not invent author names, year references, trial names, or paper "
        "citations unless they are present in the provided text.\n"
        "- If you infer something from general clinical practice, label it "
        "explicitly and do not attach bracket citations to it."
    )


def _scope_framing_instructions(question: str, answer_mode: str) -> str | None:
    if not any(pattern.search(question) for pattern in _WORKUP_QUERY_PATTERNS):
        return None

    lines = [
        "SCOPE FRAMING:",
        "- If the retrieved passages mainly cover a specific pathway, condition "
        "subset, or referral template, name that scope explicitly in the answer "
        "(for example 'For suspected rheumatoid arthritis, ...').",
        "- Do not present subtype-specific guidance as if it were a complete "
        "generic workup for all possible causes.",
        "- When the evidence is narrower than the question, say so directly in "
        "the first two sentences rather than leaving that limitation implicit.",
        "- If the indexed passages support only part of the requested workup "
        "(for example blood tests but not broad imaging guidance), state that "
        "clearly in one sentence.",
        "- Avoid broad phrasing like 'prior to referral, do X' unless the "
        "retrieved passages truly support that as a general rule for the whole "
        "clinical scenario.",
    ]
    if answer_mode == "routine_low_risk":
        lines.append(
            "- Even in routine low-risk mode, prefer scoped honesty over a "
            "confident but over-broad summary."
        )
    return "\n".join(lines)


def _matching_signals(question: str, chunk: dict) -> str:
    metadata = chunk.get("metadata", {}) or {}
    text = chunk.get("text", "")
    title = (
        metadata.get("title")
        or metadata.get("source_name")
        or metadata.get("filename")
        or ""
    )
    section = chunk.get("section_path") or metadata.get("section_title") or ""

    signals: list[str] = []
    body_overlap = query_overlap_count(question, text)
    body_phrases = phrase_overlap_count(question, text)
    title_overlap = query_overlap_count(question, title)
    title_phrases = phrase_overlap_count(question, title)
    section_overlap = query_overlap_count(question, section)
    section_phrases = phrase_overlap_count(question, section)

    if body_phrases:
        signals.append("strong phrase overlap in passage text")
    elif body_overlap >= 3:
        signals.append("high token overlap in passage text")
    elif body_overlap >= 1:
        signals.append("some token overlap in passage text")

    if title_phrases or title_overlap >= 2:
        signals.append("title closely matches the question topic")
    elif title_overlap == 1:
        signals.append("title partially matches the question topic")

    if section_phrases or section_overlap >= 2:
        signals.append("section heading closely matches the question topic")
    elif section_overlap == 1:
        signals.append("section heading partially matches the question topic")

    if not signals:
        return "broader contextual support only"
    return "; ".join(signals[:3])


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
        lines.append(
            f"{header}\n{_truncate_chunk_text(chunk.get('text', ''))}"
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
    resolved_mode = answer_mode or "strict_guideline"
    if resolved_mode not in ANSWER_MODES:
        resolved_mode = "strict_guideline"

    context_block = _format_context(question, chunks)
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

    parts = [
        _active_instructions(resolved_mode),
        _mode_instructions(resolved_mode),
        _grounding_guardrails(),
    ]
    scope_framing = _scope_framing_instructions(question, resolved_mode)
    if scope_framing:
        parts.append(scope_framing)
    if patient_block:
        parts.append(patient_block)
    if evidence_note:
        parts.append(f"EVIDENCE NOTE\n{evidence_note}")
    parts.append(f"ANSWER MODE\n{resolved_mode}")
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
    answer_mode: str | None = None,
) -> str:
    """Revise a previous answer based on specialist feedback, grounded in context.

    User-supplied strings are sanitized before prompt assembly.
    """
    original_question = _sanitize_input(original_question)
    specialist_feedback = _sanitize_input(specialist_feedback)
    if file_context:
        file_context = _sanitize_input(file_context, max_length=_MAX_INPUT_LENGTH * 2)
    resolved_mode = answer_mode or "strict_guideline"
    if resolved_mode not in ANSWER_MODES:
        resolved_mode = "strict_guideline"
    context_block = _format_context(original_question, chunks)
    has_context = bool(chunks)

    # Use the same active prompt variant as the initial generation so
    # citation and sourcing rules stay consistent across revisions.
    base_instructions = _active_instructions(resolved_mode)
    instructions = (
        f"{base_instructions}\n\n"
        f"{_mode_instructions(resolved_mode)}\n\n"
        f"{_grounding_guardrails()}\n\n"
        "A medical specialist has reviewed your previous answer and requested "
        "changes. Revise your response according to the specialist's feedback "
        "while staying grounded in the provided context.\n\n"
        "Additional revision rules:\n"
        "- Address every point raised in the specialist's feedback.\n"
        "- Do not fabricate information or cite sources that are not provided.\n"
        "- Keep the response concise and factual."
    )
    scope_framing = _scope_framing_instructions(original_question, resolved_mode)
    if scope_framing:
        instructions = f"{instructions}\n\n{scope_framing}"

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
    parts.append(f"ANSWER MODE\n{resolved_mode}")
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
