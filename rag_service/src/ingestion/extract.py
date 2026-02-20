from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

Y_TOLERANCE = 5
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
        with _open_pdf(pdf_path) as doc:
            if doc.page_count == 0:
                logger.warning(f"PDF has zero pages: {pdf_path}")
                return {
                    "source_path": pdf_path,
                    "num_pages": 0,
                    "needs_ocr": False,
                    "pages": [],
                }
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

def _extract_page(page: fitz.Page, page_number: int) -> dict[str, Any]:
    """Extract and sort text blocks from a single page.

    Args:
        page: PyMuPDF page object
        page_number: 1-indexed page number

    Returns:
        Page dict with page_number and sorted blocks
    """
    page_dict = page.get_text("dict")
    page_width = float(page.rect.width)

    raw_blocks: list[dict[str, Any]] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue

        extracted = _extract_text_block(block)
        if extracted is not None:
            raw_blocks.append(extracted)

    pass

def _extract_text_block(block: dict[str, Any]) -> dict[str, Any] | None:
    """Extract text and font metadata from a single PyMuPDF block.

    Args:
        block: Raw PyMuPDF block dict

    Returns:
        Extracted block dict, or None if block should be skipped
    """
    try:
        bbox = list(block.get("bbox", [0, 0, 0, 0]))
        lines = block.get("lines", [])

        if not lines:
            return None

        block_text: list[str] = []
        font_sizes: list[float] = []
        font_names: list[str] = []
        bold_count = 0
        total_spans = 0

        for line in lines:
            line_text = ""
            for span in line.get("spans", []):
                line_text += span.get("text", "")
                font_sizes.append(float(span.get("size", 0)))
                font_names.append(span.get("font", ""))

                if span.get("flags", 0) & 16:
                    bold_count += 1
                total_spans += 1

            block_text.append(line_text.strip())

        text = "\n".join(block_text).strip()

        if not text:
            return None

        avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 0.0
        dominant_font = (
            max(set(font_names), key=font_names.count) if font_names else ""
        )
        is_bold = (bold_count / total_spans) > 0.5 if total_spans > 0 else False

        return {
            "text": text,
            "bbox": bbox,
            "font_size": avg_font_size,
            "font_name": dominant_font,
            "is_bold": is_bold,
        }

    except Exception as e:
        logger.warning(f"Skipping malformed block: {e}")
        return None

def _detect_columns(blocks: list[dict[str, Any]], page_width: float) -> int:
    """Detect number of columns by clustering block x-positions.

    Args:
        blocks: List of raw block dicts with bbox
        page_width: Width of the page in points

    Returns:
        Number of detected columns (1 or 2)
    """
    midpoints = [
        b["bbox"][0] + (b["bbox"][2] - b["bbox"][0]) / 2
        for b in blocks
    ]
    left = [x for x in midpoints if x < page_width / 2]
    right = [x for x in midpoints if x >= page_width / 2]

    if len(left) >= 2 and len(right) >= 2:
        return 2
    return 1


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
