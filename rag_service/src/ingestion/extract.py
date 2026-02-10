# src/pdf_extract.py

# We import fitz (PyMuPDF) to read PDF files.
import fitz

# We import typing helpers for clear return types.
from typing import List, Dict

def extract_pdf_pages(pdf_path: str) -> List[Dict]:
    """
    Extracts text from each PDF page.

    Returns a list like:
    [
      {"page": 1, "text": "..."},
      {"page": 2, "text": "..."},
      ...
    ]
    """
    # Open the PDF file.
    doc = fitz.open(pdf_path)

    # Prepare a list to hold page dictionaries.
    pages = []

    # Enumerate over each page in the PDF.
    for i, page in enumerate(doc):
        # Extract plain text from the page.
        text = page.get_text("text")

        # Append page info (1-indexed page numbers are easier for citations).
        pages.append({"page": i + 1, "text": text})

    # Close the PDF to free resources.
    doc.close()

    # Return the extracted pages.
    return pages
