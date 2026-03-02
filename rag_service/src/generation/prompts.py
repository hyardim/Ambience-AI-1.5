def _format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "[1] No supporting passages found in the knowledge base."

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
    instructions = (
        "You are a cautious clinical assistant. Use only the provided context to "
        "answer the clinician's question. "
        "Cite supporting passages with the bracket numbers given in the context (e.g., [1], [2]) and only cite passages you actually use. "
        "If the context does not contain the answer, state that you do not have enough information instead of guessing. "
        "Keep the response concise and factual."
    )

    return (
        f"{instructions}\n\n"
        f"Context:\n{context_block}\n\n"
        f"Question: {question}\n\n"
        "Answer (with citations):"
    )
