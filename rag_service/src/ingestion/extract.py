from ..utils.logger import setup_logger

logger = setup_logger(__name__)

class PDFExtractionError(Exception):
    """Raised when PDF extraction fails."""
    pass
