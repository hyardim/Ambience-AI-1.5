from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

OCR_CHAR_THRESHOLD = 100


class PDFExtractionError(Exception):
    """Raised when PDF extraction fails."""

    pass

def extract_raw_document(pdf_path: str | Path) -> dict[str, Any]:
    """
    Extract text blocks from a PDF in reading order with font metadata.

    Args:
        pdf_path: Path to the PDF file (str or Path)

    Returns:
        dict: RawDocument with structure:
            {
                "source_path": str,
                "num_pages": int,
                "needs_ocr": bool,
                "pages": [
                    {
                        "page_number": int,  # 1-indexed
                        "blocks": [
                            {
                                "block_id": int,
                                "text": str,
                                "bbox": [x0, y0, x1, y1],
                                "font_size": float,
                                "font_name": str,
                                "is_bold": bool,
                            }
                        ]
                    }
                ]
            }

    Raises:
        PDFExtractionError: If PDF cannot be opened or is corrupted
    """
    pdf_path = str(pdf_path)

    try:
        with _open_pdf(pdf_path):
            pass

    except PDFExtractionError:
        raise
    except Exception as e:
        logger.error(f"Failed to extract PDF {pdf_path}: {e}")
        raise PDFExtractionError(f"Failed to open PDF: {e}") from e


def _open_pdf(pdf_path: str) -> fitz.Document:
    """Open PDF safely with specific error handling.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Opened fitz.Document (use as context manager)

    Raises:
        PDFExtractionError: With descriptive message for each failure type
    """
    try:
        return fitz.open(pdf_path)
    except FileNotFoundError as e:
        raise PDFExtractionError(f"PDF file not found: {pdf_path}") from e
    except fitz.fitz.FileDataError as e:
        raise PDFExtractionError(f"Invalid PDF: {pdf_path} - {e}") from e
    except PermissionError as e:
        raise PDFExtractionError(f"Permission denied: {pdf_path} - {e}") from e
    except Exception as e:
        raise PDFExtractionError(f"Failed to open PDF {pdf_path}: {e}") from e


def _detect_needs_ocr(pages: list[dict[str, Any]], num_pages: int) -> bool:
    """Detect scanned PDFs by checking average characters per page.

    Args:
        pages: List of extracted page dicts
        num_pages: Total number of pages in document

    Returns:
        True if document appears to be scanned/image-based
    """
    total_chars = sum(len(block["text"]) for page in pages for block in page["blocks"])
    avg_chars_per_page = total_chars / num_pages if num_pages > 0 else 0
    needs_ocr = avg_chars_per_page < OCR_CHAR_THRESHOLD

    if needs_ocr:
        logger.warning(
            f"Low text density ({avg_chars_per_page:.1f} chars/page). "
            "OCR may be needed."
        )

    return needs_ocr
