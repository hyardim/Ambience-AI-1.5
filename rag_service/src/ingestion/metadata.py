import hashlib
import os
import re
from typing import Optional, Tuple


def sha256_file(path: str) -> str:
    """Compute SHA-256 of file bytes (stable doc fingerprint)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def parse_specialty_publisher_from_path(pdf_path: str, rag_root: str) -> Tuple[str, str]:
    """Extract specialty and publisher from rag_root/<specialty>/<publisher>/file.pdf."""
    rel = os.path.relpath(pdf_path, rag_root)
    parts = rel.split(os.sep)
    if len(parts) < 3:
        raise ValueError(
            f"Expected path like rag_root/<specialty>/<publisher>/file.pdf, got: {pdf_path}"
        )
    specialty = parts[0].lower().strip()
    publisher = parts[1].lower().strip()
    return specialty, publisher


def guess_title_from_filename(filename: str) -> str:
    """Guess a title from filename without extension."""
    base = os.path.splitext(filename)[0]
    return base.strip()


def extract_published_date_from_frontmatter(front_text: str) -> Optional[str]:
    """Extract publication/updated date from early pages if present."""
    m = re.search(r"Published:\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", front_text)
    if m:
        day, month_name, year = m.group(1), m.group(2), m.group(3)
        return normalize_date(day, month_name, year)

    m = re.search(r"accepted\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", front_text, re.IGNORECASE)
    if m:
        day, month_name, year = m.group(1), m.group(2), m.group(3)
        return normalize_date(day, month_name, year)

    m = re.search(r"Produced in\s+(\d{4})", front_text, re.IGNORECASE)
    if m:
        year = m.group(1)
        return f"{year}-01-01"

    return None


def normalize_date(day: str, month_name: str, year: str) -> str:
    """Convert '28 June 2018' into '2018-06-28'."""
    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
    }
    mm = months.get(month_name.lower(), "01")
    dd = day.zfill(2)
    return f"{year}-{mm}-{dd}"
