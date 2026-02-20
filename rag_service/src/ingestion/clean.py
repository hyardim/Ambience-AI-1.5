import re
from typing import List


def clean_lines_iterative(full_text: str) -> str:
    """Line-by-line cleaner removing PDF boilerplate/noise."""
    lines = full_text.split("\n")
    cleaned_lines: List[str] = []

    page_regex = re.compile(r"Page\s+\d+(\s+of\s+\d+)?", re.IGNORECASE)
    rights_regex = re.compile(
        r"notice-of-rights|conditions#|all rights reserved|©\s*nice|©\s*the author",
        re.IGNORECASE,
    )
    url_regex = re.compile(r"https?://|www\.|")
    meta_regex = re.compile(r"(doi:\s*10\.\d+|e-mail:\s+\S+|Email:\s+\S+)", re.IGNORECASE)
    toc_regex = re.compile(r"\.{4,}")

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        line_clean = page_regex.sub("", line_clean)
        line_clean = meta_regex.sub("", line_clean)
        line_clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]", " ", line_clean)

        if rights_regex.search(line_clean):
            continue
        if url_regex.search(line_clean):
            continue
        if toc_regex.search(line_clean):
            continue

        if len(line_clean) > 5:
            cleaned_lines.append(line_clean)

    return " ".join(cleaned_lines)


def fix_stuttering_headers(text: str) -> str:
    """Fix duplicated first word (e.g., 'Warfarin Warfarin')."""
    words = text.split()
    if len(words) > 1 and words[0].lower() == words[1].lower():
        return " ".join(words[1:])
    return text
