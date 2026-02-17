import logging
from typing import Any

import fitz  # PyMuPDF

# Configure logging for this module
logger = logging.getLogger(__name__)


class PDFExtractionError(Exception):
    """
    Raised when PDF extraction fails.

    This includes cases where:
    - PDF file cannot be opened (corrupted, missing, permission denied)
    - PDF is encrypted and we cannot access content
    - Internal PyMuPDF errors during text extraction
    """

    pass


def extract_raw_document(pdf_path: str) -> dict[str, Any]:
    """
    Extract text blocks from a PDF in reading order with font metadata.

    This is the main entry point for PDF extraction. It processes a PDF file
    and returns a structured representation suitable for downstream text
    cleaning, chunking, and heading detection.

    The function handles:
    - Multi-column layouts (2 columns work well; 3+ may need enhancement)
    - Font metadata extraction for heading detection
    - Scanned PDF detection (sets needs_ocr flag)
    - Empty and corrupted PDFs (with appropriate error handling)

    Args:
        pdf_path (str): Absolute or relative path to the PDF file to extract.
                       Example: "data/guidelines/diabetes.pdf"

    Returns:
        dict: A RawDocument structure containing:
            - source_path (str): Original PDF path for provenance
            - num_pages (int): Total number of pages in the PDF
            - needs_ocr (bool): True if PDF appears to be scanned/image-based
            - pages (List[dict]): List of page objects, each containing:
                - page_number (int): 1-indexed page number
                - blocks (List[dict]): Sorted text blocks, each with:
                    - block_id (int): Sequential ID within page (0, 1, 2, ...)
                    - text (str): Extracted text content
                    - bbox (List[float]): [x0, y0, x1, y1] bounding box
                    - font_size (float): Average font size in points
                    - font_name (str): Dominant font name
                    - is_bold (bool): True if majority of text is bold

    Raises:
        PDFExtractionError: If PDF cannot be opened, is corrupted, or extraction
                          fails catastrophically. Empty PDFs return valid empty
                          structure rather than raising an exception.

    Example:
        >>> result = extract_raw_document("guidelines/diabetes.pdf")
        >>> print(f"Extracted {result['num_pages']} pages")
        >>> print(f"First block: {result['pages'][0]['blocks'][0]['text']}")

    Note:
        - This function does NOT perform text cleaning (headers/footers removal)
        - This function does NOT implement OCR (only detects need for it)
        - Table cells may not be in perfect reading order (Issue #6 will handle)
    """

    # Step 1: Open PDF and validate
    doc = _open_pdf(pdf_path)

    # Handle empty PDFs gracefully
    if doc.page_count == 0:
        return {
            "source_path": pdf_path,
            "num_pages": 0,
            "needs_ocr": False,
            "pages": [],
        }


def _open_pdf(pdf_path: str) -> fitz.Document:
    """
    Open a PDF file and validate it's readable.

    This handles common failure modes:
    - File not found
    - File is not a valid PDF
    - File is corrupted
    - Insufficient permissions

    Args:
        pdf_path (str): Path to PDF file

    Returns:
        fitz.Document: Opened PyMuPDF document object

    Raises:
        PDFExtractionError: If PDF cannot be opened for any reason
    """
    try:
        # fitz.open() can handle file paths, file-like objects, or bytes
        doc = fitz.open(pdf_path)
        return doc
    except FileNotFoundError:
        # File doesn't exist at the specified path
        raise PDFExtractionError(f"PDF file not found: {pdf_path}")
    except fitz.fitz.FileDataError as e:
        # File exists but is corrupted or not a valid PDF
        raise PDFExtractionError(f"Invalid or corrupted PDF: {pdf_path} - {e}")
    except PermissionError as e:
        # File exists but we don't have permission to read it
        raise PDFExtractionError(f"Permission denied reading PDF: {pdf_path} - {e}")
    except Exception as e:
        # Catch-all for any other unexpected errors
        raise PDFExtractionError(f"Failed to open PDF {pdf_path}: {e}")
