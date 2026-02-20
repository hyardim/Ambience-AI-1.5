import fitz
from typing import Dict, List


def extract_pdf_pages(pdf_path: str) -> List[Dict]:
    """Extract plain text from each PDF page."""
    doc = fitz.open(pdf_path)
    pages: List[Dict] = []

    for i, page in enumerate(doc):
        text = page.get_text("text")
        pages.append({"page": i + 1, "text": text})

    doc.close()
    return pages
