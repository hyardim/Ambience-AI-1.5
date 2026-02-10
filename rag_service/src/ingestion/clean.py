# src/clean.py

# Import regex for cleaning patterns.
import re

# Import typing.
from typing import List, Tuple

def clean_lines_iterative(full_text: str) -> str:
    """
    Line-by-line cleaner that removes common PDF boilerplate/noise.
    (This is adapted from your code, with the same spirit.)
    """
    # Split into lines.
    lines = full_text.split("\n")

    # We'll store cleaned lines here.
    cleaned_lines = []

    # Regex: "Page X of Y"
    page_regex = re.compile(r"Page\s+\d+(\s+of\s+\d+)?", re.IGNORECASE)

    # Regex: rights/boilerplate
    rights_regex = re.compile(
        r"notice-of-rights|conditions#|all rights reserved|©\s*nice|©\s*the author",
        re.IGNORECASE,
    )

    # Regex: URLs
    url_regex = re.compile(r"https?://|www\.|available at|accessed on", re.IGNORECASE)

    # Regex: DOI / emails
    meta_regex = re.compile(r"(doi:\s*10\.\d+|e-mail:\s+\S+|Email:\s+\S+)", re.IGNORECASE)

    # Regex: TOC dot leaders (....)
    toc_regex = re.compile(r"\.{4,}")

    for line in lines:
        # Strip whitespace.
        line_clean = line.strip()

        # Skip empty lines.
        if not line_clean:
            continue

        # Remove page markers and metadata fragments.
        line_clean = page_regex.sub("", line_clean)
        line_clean = meta_regex.sub("", line_clean)

        # Remove weird binary/control chars that sometimes appear.
        line_clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]", " ", line_clean)

        # Kill obvious boilerplate lines.
        if rights_regex.search(line_clean):
            continue
        if url_regex.search(line_clean):
            continue
        if toc_regex.search(line_clean):
            continue

        # Keep reasonably sized lines.
        if len(line_clean) > 5:
            cleaned_lines.append(line_clean)

    # Join back into one text block.
    return " ".join(cleaned_lines)

def fix_stuttering_headers(text: str) -> str:
    """
    Fixes duplicated first word: 'Warfarin Warfarin ...'
    """
    words = text.split()
    if len(words) > 1 and words[0].lower() == words[1].lower():
        return " ".join(words[1:])
    return text
