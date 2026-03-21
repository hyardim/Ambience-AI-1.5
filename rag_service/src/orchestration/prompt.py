from ..retrieval.citation import CitedResult, format_section_path


def build_system_prompt() -> str:
    return (
        "You are a clinical assistant. Answer only from the provided context. "
        "Use inline citation markers like [1], [2] that refer to the numbered sources. "
        "If the context lacks the needed information, say so explicitly. "
        "Be concise and clinically precise; do not use outside knowledge."
    )


def format_context(context: list[CitedResult]) -> str:
    if not context:
        return ""

    blocks: list[str] = []
    for idx, item in enumerate(context, start=1):
        citation = item.citation
        section = format_section_path(citation.section_path)
        header = (
            f"[{idx}] {citation.title} — {citation.source_name} ({citation.specialty})"
        )
        meta = (
            f"Section: {citation.section_title} | {section} | "
            f"Pages: {citation.page_start}-{citation.page_end}"
        )
        block = f"{header}\n{meta}\n---\n{item.text.strip()}"
        blocks.append(block)

    return "\n\n".join(blocks)
