"""Orchestration-level prompt helpers.

NOTE: This module provides a *lightweight* system prompt and context formatter
used by the orchestration layer (e.g. for streaming or chat-completion
wrappers that supply a separate ``system`` message).  The **canonical**,
feature-complete prompt builder lives in ``generation.prompts`` which handles
patient context, file uploads, evidence notes, prompt variants, and injection
sanitization.  If you need the full grounded prompt, prefer
``generation.prompts.build_grounded_prompt`` instead of duplicating logic here.
"""

from ..generation.prompts import _active_instructions
from ..retrieval.citation import CitedResult, format_section_path


def build_system_prompt() -> str:
    """Return the active system-level instruction string.

    Delegates to ``generation.prompts._active_instructions()`` so both code
    paths use the same prompt variant (controlled by ``ACTIVE_PROMPT``).
    """
    return _active_instructions()


def format_context(context: list[CitedResult]) -> str:
    """Format cited retrieval results into a numbered context block.

    This is a *slim* formatter for orchestration use.  The generation-layer
    equivalent is ``generation.prompts._format_context``.
    """
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
