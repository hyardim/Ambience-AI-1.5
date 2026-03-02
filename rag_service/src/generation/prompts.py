def _format_context(chunks: list[dict]) -> str:
    """Render retrieved chunks for the prompt. Empty string when none."""
    if not chunks:
        return ""

    lines = []
    for idx, chunk in enumerate(chunks, start=1):
        source = chunk.get("metadata", {}).get("filename", "Unknown Source")
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
        "If there is no relevant context, respond briefly that you do not have enough information and do not cite sources. "
        "Keep the response concise and factual."
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
