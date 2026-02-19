import fitz  # PyMuPDF

from ..utils.logger import setup_logger

logger = setup_logger(__name__)


class PDFExtractionError(Exception):
    """Raised when PDF extraction fails."""

    pass


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
