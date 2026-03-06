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
    "Cite supporting passages with the bracket numbers given in the context "
    "(e.g., [1], [2]) and only cite passages you actually use. "
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
    "2. SUPPLEMENTARY KNOWLEDGE: You may use general clinical knowledge to fill gaps the indexed "
    "passages do not address. Keep this clearly separate — never mix it with cited content or "
    "attach citation numbers to it.\n"
    "3. HONEST SCOPE: If the indexed passages do not cover the question's topic, say so in one sentence, "
    "then continue with the General Clinical Knowledge section only.\n"
    "4. NO FABRICATION: Do not invent drug doses, statistics, guideline codes, study references, "
    "author names, or year references — not even for well-known studies. "
    "If you are uncertain, say so explicitly.\n\n"

    "Response format:\n"
    "First, write only statements that are directly supported by the indexed passages, each cited with [N]. "
    "Do NOT include any statistic, percentage, risk factor, or clinical claim in this section unless it "
    "appears in an indexed passage and you are citing it. If a claim is not in an indexed passage, it "
    "does not belong here — move it to the general block below.\n"
    "Then, if there is additional useful context from general medical knowledge, add a single paragraph "
    "starting with exactly: 'General clinical context:' — no citation numbers, no statistics, no author names. "
    "If the indexed evidence fully covers the question, omit this block entirely.\n"
    "End with one or two sentences on safety flags or monitoring."
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
            f"[{idx}] {chunk.get('text', '').strip()}\nSource: {source}{page_note}"
        )

    return "\n\n".join(lines)


def build_grounded_prompt(question: str, chunks: list[dict]) -> str:
    context_block = _format_context(chunks)
    has_context = bool(chunks)

    context_section = "Context:\n" + (context_block if has_context else "(none)")
    citation_hint = (
        "Answer (with citations):" if has_context else "Answer (no citations):"
    )

    return (
        f"{_INSTRUCTIONS}\n\n"
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
