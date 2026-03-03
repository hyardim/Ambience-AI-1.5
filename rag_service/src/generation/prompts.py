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


def build_grounded_prompt(question: str, chunks: list[dict]) -> str:
    context_block = _format_context(chunks)
    has_context = bool(chunks)
    instructions = (
        "You are a cautious clinical assistant. Use only the provided context to "
        "answer the clinician's question. "
        "Cite supporting passages with the bracket numbers given in the context (e.g., [1], [2]) and only cite passages you actually use. "
        "If there is no relevant context or the question appears non-medical/off-topic (e.g., small talk), politely state that you cannot provide clinical guidance without relevant medical context. "
        "Do not fabricate context or cite sources when none are available. Keep the response concise and factual."
    )

    context_section = "Context:\n" + (context_block if has_context else "(none)")
    citation_hint = (
        "Answer (with citations):" if has_context else "Answer (no citations):"
    )

    return (
        f"{instructions}\n\n"
        f"{context_section}\n\n"
        f"Question: {question}\n\n"
        f"{citation_hint}"
    )


def build_revision_prompt(
    original_question: str,
    previous_answer: str,
    specialist_feedback: str,
    chunks: list[dict],
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

    context_section = "Context:\n" + (context_block if has_context else "(none)")
    citation_hint = (
        "Revised answer (with citations):" if has_context else "Revised answer (no citations):"
    )

    return (
        f"{instructions}\n\n"
        f"{context_section}\n\n"
        f"Original question: {original_question}\n\n"
        f"Previous answer: {previous_answer}\n\n"
        f"Specialist feedback: {specialist_feedback}\n\n"
        f"{citation_hint}"
    )
