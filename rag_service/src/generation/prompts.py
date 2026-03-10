MAX_CHARS_PER_CHUNK = 1200


def _truncate_chunk_text(text: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 14].rstrip() + " …[truncated]"

# ---------------------------------------------------------------------------
# PROMPT VARIANT TOGGLE
# Set ACTIVE_PROMPT = "original" to use the strict citation-only prompt.
# Set ACTIVE_PROMPT = "new"      to use the balanced health-LLM prompt.
# ---------------------------------------------------------------------------
ACTIVE_PROMPT = "new"

# ---------------------------------------------------------------------------
# Variant A — original: strict, context-only, refuses when no sources found
# ---------------------------------------------------------------------------
_INSTRUCTIONS_ORIGINAL = (
    "You are a cautious clinical assistant. Use only the provided context to "
    "answer the clinician's question. "
    "Cite supporting passages with the bracket numbers given in the Context section "
    "(e.g., [1], [2]) and only cite passages you actually use. "
    "Do NOT use bracket numbers for uploaded documents — cite them as 'Uploaded document' instead. "
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
    "The indexed guideline passages below are your PRIMARY and most authoritative source. "
    "Your general clinical knowledge plays a SUPPLEMENTARY role only — use it to explain terminology, "
    "provide clinical context, or bridge small gaps in the indexed evidence, never to replace it.\n\n"

    "Rules for answering:\n"
    "1. INDEXED CITATIONS FIRST: Base your answer on the indexed passages. "
    "Cite them with [1], [2] etc. only when a passage directly supports the specific claim you are making. "
    "Read each passage carefully — if it covers a different condition or topic than the question, "
    "do not cite it, even if it contains a related keyword.\n"
    "2. UPLOADED DOCUMENTS: If an 'UPLOADED DOCUMENTS' section is present, it contains patient-specific "
    "files (e.g. a guideline PDF or clinical document). Use this content to answer the question. "
    "Cite it as 'Uploaded document' — do NOT use bracket numbers for it.\n"
    "3. SUPPLEMENTARY KNOWLEDGE: You may use general clinical knowledge to fill gaps the indexed "
    "passages do not address. Keep this clearly separate — never mix it with cited content or "
    "attach citation numbers to it.\n"
    "4. HONEST SCOPE: If the indexed passages do not cover the question's topic, say so in one sentence, "
    "then continue with the 'General clinical context:' section only.\n"
    "5. NO FABRICATION: Do not invent drug doses, statistics, guideline codes, study references, "
    "author names, or year references — not even for well-known studies. "
    "If you are uncertain, say so explicitly.\n"
    "6. CONFLICTING SOURCES: If an uploaded document contradicts an indexed guideline passage, "
    "flag the discrepancy explicitly (e.g. 'Note: the uploaded document states X, whereas the indexed "
    "guideline states Y').\n\n"

    "Response format:\n"
    "First, write only statements that are directly supported by the indexed passages, each cited with [N]. "
    "Do NOT include any statistic, percentage, risk factor, or clinical claim in this section unless it "
    "appears in an indexed passage and you are citing it. If a claim is not in an indexed passage, it "
    "does not belong here — move it to the general block below.\n"
    "Then, if there is additional useful context from general medical knowledge, add a single paragraph "
    "starting with exactly: 'General clinical context:' — no citation numbers, no statistics, no author names. "
    "If the indexed evidence fully covers the question, omit this block entirely.\n"
    "If safety considerations apply to this question, end with one or two sentences on relevant safety flags or monitoring. "
    "If there are no safety implications, omit this section entirely."
)

# Active selection — change ACTIVE_PROMPT above to switch
_INSTRUCTIONS = _INSTRUCTIONS_NEW if ACTIVE_PROMPT == "new" else _INSTRUCTIONS_ORIGINAL


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
            f"[{idx}] {_truncate_chunk_text(chunk.get('text', ''))}\nSource: {source}{page_note}"
        )

    return "\n\n".join(lines)


def _format_patient_context(patient_context: dict | None) -> str:
    """Render patient demographics block, or empty string when not provided."""
    if not patient_context:
        return ""
    parts = []
    if patient_context.get("age"):
        parts.append(f"Age: {patient_context['age']}")
    if patient_context.get("gender"):
        parts.append(f"Gender: {patient_context['gender'].capitalize()}")
    if patient_context.get("specialty"):
        parts.append(f"Specialty: {patient_context['specialty'].capitalize()}")
    if patient_context.get("severity"):
        parts.append(f"Severity: {patient_context['severity'].capitalize()}")
    header = "  |  ".join(parts)
    notes = patient_context.get("notes", "")
    block = "PATIENT CONTEXT\n" + header
    if notes:
        block += f"\nClinical notes: {notes}"
    return block


def build_grounded_prompt(
    question: str,
    chunks: list[dict],
    patient_context: dict | None = None,
    file_context: str | None = None,
) -> str:
    context_block = _format_context(chunks)
    has_context = bool(chunks)
    has_files = bool(file_context)

    patient_block = _format_patient_context(patient_context)
    # Numbered context comes first so [1][2]... anchor to indexed passages only.
    context_section = "Context:\n" + (context_block if has_context else "(none)")
    citation_hint = (
        "Answer (with citations):" if (has_context or has_files) else "Answer (no citations):"
    )

    parts = [_INSTRUCTIONS]
    if patient_block:
        parts.append(patient_block)
    parts.append(context_section)
    # Uploaded documents come after numbered context; cited as 'Uploaded document', not [N].
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
) -> str:
    """Revise a previous answer based on specialist feedback, grounded in context."""
    context_block = _format_context(chunks)
    has_context = bool(chunks)

    instructions = (
        "You are a cautious clinical assistant. A medical specialist has reviewed "
        "your previous answer and requested changes. Revise your response according "
        "to the specialist's feedback while staying grounded in the provided context.\n\n"
        "Rules:\n"
        "- Use only the provided context passages to support your revised answer.\n"
        "- Cite supporting passages with the bracket numbers given in the context (e.g., [1], [2]) and only cite passages you actually use.\n"
        "- Do NOT use bracket numbers for uploaded documents — cite them as 'Uploaded document' instead.\n"
        "- Address every point raised in the specialist's feedback.\n"
        "- Do not fabricate information or cite sources that are not provided.\n"
        "- Keep the response concise and factual."
    )

    patient_block = _format_patient_context(patient_context)
    context_section = "Context:\n" + (context_block if has_context else "(none)")
    has_files = bool(file_context)
    citation_hint = (
        "Revised answer (with citations):" if (has_context or has_files) else "Revised answer (no citations):"
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
