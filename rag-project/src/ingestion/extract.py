"""
PDF text extraction module for the ingestion pipeline.

This module extracts text blocks from PDF files in reading order, preserving
layout information and font metadata for downstream processing.

The extraction process:
1. Opens PDF and validates it's processable
2. Extracts text blocks with position and font information
3. Sorts blocks into human reading order (top-to-bottom, left-to-right)
4. Detects if PDF needs OCR (scanned documents)
5. Returns structured data with complete provenance information

Author: Medical Guidelines RAG System
Date: 2024
"""

import fitz  # PyMuPDF
from typing import Dict, List, Any, Tuple
import logging

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


def extract_raw_document(pdf_path: str) -> Dict[str, Any]:
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
        logger.warning(f"PDF has zero pages: {pdf_path}")
        return {
            "source_path": pdf_path,
            "num_pages": 0,
            "needs_ocr": False,
            "pages": []
        }
    
    # Step 2: Extract all pages
    pages = []
    for page_num in range(doc.page_count):
        # PyMuPDF uses 0-indexed pages internally, but we expose 1-indexed
        page = doc[page_num]
        page_data = _extract_page(page, page_num + 1)  # Convert to 1-indexed
        pages.append(page_data)
    
    # Step 3: Detect if PDF needs OCR (scanned documents have very little text)
    needs_ocr = _detect_needs_ocr(pages, doc.page_count)
    
    # Clean up: close the PDF document
    doc.close()
    
    # Step 4: Return structured result
    return {
        "source_path": pdf_path,
        "num_pages": doc.page_count,
        "needs_ocr": needs_ocr,
        "pages": pages
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


def _extract_page(page: fitz.Page, page_number: int) -> Dict[str, Any]:
    """
    Extract all text blocks from a single PDF page.
    
    This function:
    1. Gets raw text blocks with position data from PyMuPDF
    2. Filters to keep only text blocks (ignoring images/drawings)
    3. Extracts font metadata from each block
    4. Sorts blocks into reading order
    5. Assigns sequential block IDs
    
    Args:
        page (fitz.Page): PyMuPDF page object to extract from
        page_number (int): 1-indexed page number for the result
    
    Returns:
        dict: Page structure containing:
            - page_number (int): The 1-indexed page number
            - blocks (List[dict]): Sorted list of text blocks with metadata
    
    Note:
        This function preserves line breaks within blocks (\n characters)
        but does NOT perform cleaning of headers, footers, or noise text.
    """
    # Get dictionary representation of page with all layout information
    # This includes blocks, lines, spans (text runs with same font), bbox, etc.
    page_dict = page.get_text("dict")
    
    # Extract raw blocks from the page dictionary
    raw_blocks = []
    for block in page_dict.get("blocks", []):
        # Filter: keep only text blocks (type 0)
        # type 0 = text block
        # type 1 = image/figure block (ignored for now; Issue #4 may handle figures)
        # Other types = drawings, etc. (also ignored)
        if block.get("type") != 0:
            continue
        
        # Extract the text block with font metadata
        extracted_block = _extract_text_block(block)
        
        # Skip blocks that have no extractable text
        # This can happen with malformed PDFs or blocks that are just whitespace
        if extracted_block is None or not extracted_block["text"].strip():
            continue
        
        raw_blocks.append(extracted_block)
    
    # Sort blocks into reading order (top-to-bottom, left-to-right)
    sorted_blocks = _sort_blocks_reading_order(raw_blocks)
    
    # Assign sequential block IDs after sorting
    for idx, block in enumerate(sorted_blocks):
        block["block_id"] = idx
    
    return {
        "page_number": page_number,
        "blocks": sorted_blocks
    }


def _extract_text_block(block: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract text and font metadata from a single PyMuPDF text block.
    
    A PyMuPDF block contains multiple lines, and each line contains multiple
    spans (runs of text with the same font). We iterate through this hierarchy
    to build the complete text and calculate aggregate font metadata.
    
    Font metadata is used downstream for:
    - Heading detection (Issue #5): larger font_size indicates headings
    - Bold detection: is_bold helps identify emphasized text
    - Font consistency: font_name can help detect section boundaries
    
    Args:
        block (dict): PyMuPDF block dictionary containing:
            - bbox: [x0, y0, x1, y1] bounding box
            - lines: list of line dictionaries, each containing:
                - spans: list of span dictionaries with text and font info
    
    Returns:
        dict: Extracted block with structure:
            - text (str): Complete text with line breaks preserved
            - bbox (List[float]): [x0, y0, x1, y1] position on page
            - font_size (float): Average font size in points (0.0 if undetectable)
            - font_name (str): Most common font name ("" if undetectable)
            - is_bold (bool): True if >50% of spans are bold (False if undetectable)
        
        Returns None if block has no lines or spans (malformed block).
    
    Note:
        PyMuPDF handles Unicode correctly by default, including:
        - Mathematical symbols: ≥, ≤, ±, μ (common in medical texts)
        - Superscripts/subscripts: m², CO₂ (units and formulas)
        - Ligatures: fi, fl (automatically expanded)
        No special processing is needed for these characters.
    """
    # Get bounding box: [x0, y0, x1, y1] where (x0,y0) is top-left
    bbox = block.get("bbox", [0, 0, 0, 0])
    
    # Lists to accumulate text and font information from all spans
    block_text = []  # One string per line
    font_sizes = []  # Font size of each span (for averaging)
    font_names = []  # Font name of each span (for majority vote)
    bold_count = 0   # Number of bold spans
    total_spans = 0  # Total number of spans (for bold percentage)
    
    # Iterate through lines in the block
    lines = block.get("lines", [])
    if not lines:
        # Malformed block with no lines - skip it
        return None
    
    for line in lines:
        line_text = ""
        
        # Iterate through spans (text runs with same formatting) in the line
        spans = line.get("spans", [])
        for span in spans:
            # Append text from this span
            # PyMuPDF returns text as Unicode string, correctly handling special chars
            line_text += span.get("text", "")
            
            # Extract font metadata from the span
            # size: font size in points (e.g., 12.0)
            font_sizes.append(span.get("size", 0))
            
            # font: font name (e.g., "Arial", "Times-Bold")
            font_names.append(span.get("font", ""))
            
            # flags: bit field indicating text properties
            # Bit 4 (value 16 = 2^4): indicates superscript
            # Bit 5 (value 32 = 2^5): indicates italic
            # Bit 6 (value 64 = 2^6): indicates bold  ← This is what we check
            # Check if bold flag is set: (flags & 16) for old PyMuPDF or (flags & 2^4)
            # Note: PyMuPDF documentation uses flags & 16 for bold, but this can vary
            # We use flags & 16 as documented in PyMuPDF docs
            flags = span.get("flags", 0)
            if flags & 16:  # Bold flag
                bold_count += 1
            
            total_spans += 1
        
        # Add this line's text to the block (preserve line breaks)
        block_text.append(line_text.strip())
    
    # Join all lines with newlines to preserve paragraph structure
    text = "\n".join(block_text).strip()
    
    # Calculate aggregate font metadata
    # Average font size across all spans
    avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 0.0
    
    # Dominant font name (most common font in the block)
    # This uses majority vote: the font that appears most frequently
    if font_names:
        dominant_font = max(set(font_names), key=font_names.count)
    else:
        dominant_font = ""
    
    # Bold detection: block is bold if >50% of spans are bold
    # This is a simple heuristic that works well for heading detection
    is_bold = (bold_count / total_spans) > 0.5 if total_spans > 0 else False
    
    return {
        "text": text,
        "bbox": list(bbox),  # Convert tuple to list for JSON serialization
        "font_size": avg_font_size,
        "font_name": dominant_font,
        "is_bold": is_bold
    }


def _sort_blocks_reading_order(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort text blocks into human reading order (top-to-bottom, left-to-right).
    
    This is critical for multi-column layouts. Without sorting, text from
    the right column gets interleaved with text from the left column, making
    the output unreadable.
    
    Algorithm:
    1. Sort primarily by vertical position (y-coordinate)
    2. Within similar y-positions, sort by horizontal position (x-coordinate)
    3. Use tolerance for y-position to handle coordinate jitter
    
    The y-tolerance groups blocks that are visually aligned on the same
    horizontal line, even if their y-coordinates differ slightly due to
    baseline variations or PDF rendering quirks.
    
    Args:
        blocks (List[dict]): Unsorted list of blocks, each with a 'bbox' field
                           bbox format: [x0, y0, x1, y1] where:
                           - (x0, y0) is top-left corner
                           - (x1, y1) is bottom-right corner
    
    Returns:
        List[dict]: Same blocks, sorted in reading order
    
    Note:
        This works well for:
        - Single column layouts
        - 2-column layouts
        - Simple documents
        
        Known limitations:
        - 3+ column layouts may need x-position clustering
        - Tables cells may not sort row-by-row (column-by-column instead)
        - Text wrapping around figures may not be perfect
        
        These limitations are acceptable for v1. Issue #6 will handle tables,
        and complex layouts can be enhanced later if needed.
    """
    # Define y-position tolerance in points
    # 5 points is roughly 1.75mm, which handles most baseline variations
    # while still distinguishing between different lines
    Y_TOLERANCE = 5
    
    # Sort blocks by:
    # 1. Primary key: y-position bucket (top to bottom)
    #    We round y0/tolerance to bucket nearby y-values together
    #    Example: y0=100 and y0=102 both map to bucket 20 (with tolerance=5)
    # 2. Secondary key: x-position (left to right)
    #    Within the same y-bucket, sort by x0 (left edge)
    sorted_blocks = sorted(
        blocks,
        key=lambda b: (
            round(b["bbox"][1] / Y_TOLERANCE),  # bbox[1] is y0 (top edge)
            b["bbox"][0]                         # bbox[0] is x0 (left edge)
        )
    )
    
    return sorted_blocks


def _detect_needs_ocr(pages: List[Dict[str, Any]], num_pages: int) -> bool:
    """
    Detect if a PDF is scanned/image-based and needs OCR.
    
    Scanned PDFs contain images of pages rather than extractable text.
    They appear as PDFs but yield very little or no text when extracted.
    
    This function uses a simple heuristic: calculate average characters per page.
    If it's suspiciously low, the PDF is likely scanned.
    
    Threshold rationale:
    - Normal text PDF: ~2000+ characters per page (typical paragraph has ~500 chars)
    - Scanned PDF: 0-50 characters per page (maybe some OCR'd headers/footers)
    - Threshold of 100: conservative safety margin
    
    Args:
        pages (List[dict]): Extracted pages, each containing blocks with text
        num_pages (int): Total number of pages in the PDF
    
    Returns:
        bool: True if PDF appears to be scanned and needs OCR, False otherwise
    
    Note:
        We DO NOT implement OCR in this module. We only set a flag for
        downstream stages or manual review. The pipeline will skip OCR
        processing for now but flag these documents for future enhancement.
    """
    # Count total characters across all blocks in all pages
    total_chars = 0
    for page in pages:
        for block in page["blocks"]:
            # Count characters in the text (excluding whitespace)
            total_chars += len(block["text"])
    
    # Calculate average characters per page
    avg_chars_per_page = total_chars / num_pages if num_pages > 0 else 0
    
    # Apply threshold: <100 chars/page suggests scanned PDF
    needs_ocr = avg_chars_per_page < 100
    
    if needs_ocr:
        logger.warning(
            f"PDF appears to be scanned (avg {avg_chars_per_page:.1f} chars/page). "
            f"OCR may be needed for full text extraction."
        )
    
    return needs_ocr