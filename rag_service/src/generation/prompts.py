def _format_context(chunks: list[dict]) -> str:
    """Render retrieved chunks for the prompt. Empty string when none."""
    if not chunks:
        return ""

    lines = []
    for idx, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata", {}) or {}
        # Prefer human-friendly labels; fall back to filename when present, otherwise mark unknown.
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
            f"[{idx}] {chunk.get('text', '').strip()}\nSource: {source}{page_note}"
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
    instructions = (
        "You are a cautious clinical assistant. Use only the provided context to "
        "answer the clinician's question. "
        "Cite supporting passages with the bracket numbers given in the context (e.g., [1], [2]) and only cite passages you actually use. "
        "When referencing content from uploaded documents, cite them as 'Uploaded document'. "
        "If there is no relevant context or the question appears non-medical/off-topic (e.g., small talk), politely state that you cannot provide clinical guidance without relevant medical context. "
        "Do not fabricate context or cite sources when none are available. Keep the response concise and factual."
    )

    patient_block = _format_patient_context(patient_context)
    context_section = "Context:\n" + (context_block if has_context else "(none)")
    citation_hint = (
        "Answer (with citations):" if (has_context or has_files) else "Answer (no citations):"
    )

    parts = [instructions]
    if patient_block:
        parts.append(patient_block)
    if file_context:
        parts.append(f"UPLOADED DOCUMENTS\n{file_context}")
    parts += [context_section, f"Question: {question}", citation_hint]
    return "\n\n".join(parts)


def build_revision_prompt(
    original_question: str,
    previous_answer: str,
    specialist_feedback: str,
    chunks: list[dict],
    patient_context: dict | None = None,
    file_context: str | None = None,
) -> str:
    """Build a prompt that asks the model to revise a previous answer based on
    specialist feedback, grounded in the same (or refreshed) retrieved context."""
    context_block = _format_context(chunks)
    has_context = bool(chunks)

    instructions = (
        "You are a cautious clinical assistant. A medical specialist has reviewed "
        "your previous answer and requested changes. Revise your response according "
        "to the specialist's feedback while staying grounded in the provided context.\n\n"
        "Rules:\n"
        "- Use only the provided context passages to support your revised answer.\n"
        "- Cite supporting passages with the bracket numbers given in the context (e.g., [1], [2]) and only cite passages you actually use.\n"
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
    if file_context:
        parts.append(f"UPLOADED DOCUMENTS\n{file_context}")
    parts += [
        context_section,
        f"Original question: {original_question}",
        f"Previous answer: {previous_answer}",
        f"Specialist feedback: {specialist_feedback}",
        citation_hint,
    ]
    return "\n\n".join(parts)
