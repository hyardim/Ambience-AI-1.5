from __future__ import annotations

import hashlib
import os
from datetime import date
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

VALID_SPECIALTIES = {"neurology", "rheumatology"}
VALID_SOURCE_NAMES = {"NICE", "BSR", "Others"}
VALID_DOC_TYPES = {"guideline", "protocol", "policy", "standard"}


class MetadataValidationError(Exception):
    """Raised when metadata validation fails."""

    pass


def attach_metadata(
    table_aware_doc: dict[str, Any],
    source_info: dict[str, Any],
) -> dict[str, Any]:
    """
    Attach complete metadata at document and block levels.

    Args:
        table_aware_doc: TableAwareDocument dict from table_detect.py
        source_info: Dict containing external metadata (see source_info schema)

    Returns:
        dict: MetadataDocument with doc_meta and block_uid on every block

    Raises:
        MetadataValidationError: If required metadata is missing or invalid

    Processing steps:
        1. Infer specialty/source_name from path if not provided
        2. Validate source_info
        3. Extract PDF metadata from source file
        4. Generate doc_id (stable, content-based)
        5. Generate doc_version (detects updates)
        6. Extract or infer title
        7. Create doc_meta object
        8. For each block, generate block_uid
        9. Validate all metadata
    """
    pass


def infer_from_path(source_path: str) -> dict[str, str]:
    """Infer specialty and source_name from file path structure.

    Expected path pattern: .../raw/{specialty}/{source_name}/{filename}.pdf

    Args:
        source_path: File path to the PDF

    Returns:
        Dict with 'specialty' and 'source_name' if inferable, else empty strings
    """
    parts = Path(source_path).parts
    try:
        raw_index = parts.index("raw")
        return {
            "specialty": parts[raw_index + 1],
            "source_name": parts[raw_index + 2],
        }
    except (ValueError, IndexError):
        return {"specialty": "", "source_name": ""}


def validate_source_info(source_info: dict[str, Any]) -> None:
    """Validate source_info fields.

    Args:
        source_info: Caller-supplied source info dict

    Raises:
        MetadataValidationError: If any required field is missing or invalid
    """
    required = ["source_name", "source_path", "doc_type", "specialty"]
    for field in required:
        if not source_info.get(field):
            raise MetadataValidationError(
                f"source_info missing required field: {field}"
            )

    if source_info["specialty"] not in VALID_SPECIALTIES:
        raise MetadataValidationError(
            f"Invalid specialty '{source_info['specialty']}'. "
            f"Must be one of: {VALID_SPECIALTIES}"
        )

    if source_info["source_name"] not in VALID_SOURCE_NAMES:
        raise MetadataValidationError(
            f"Invalid source_name '{source_info['source_name']}'. "
            f"Must be one of: {VALID_SOURCE_NAMES}"
        )

    if source_info["doc_type"] not in VALID_DOC_TYPES:
        raise MetadataValidationError(
            f"Invalid doc_type '{source_info['doc_type']}'. "
            f"Must be one of: {VALID_DOC_TYPES}"
        )


def extract_pdf_metadata(pdf_path: str) -> dict[str, Any]:
    """Extract metadata from PDF file using PyMuPDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Dict with keys: title, author, subject, creator, producer,
        creationDate, modDate, uid
    """
    try:
        with fitz.open(pdf_path) as doc:
            metadata = doc.metadata
            return {
                "title": metadata.get("title", ""),
                "author": metadata.get("author", ""),
                "subject": metadata.get("subject", ""),
                "creator": metadata.get("creator", ""),
                "producer": metadata.get("producer", ""),
                "creationDate": parse_pdf_date(metadata.get("creationDate", "")),
                "modDate": parse_pdf_date(metadata.get("modDate", "")),
                "uid": metadata.get("uid", ""),
            }
    except Exception as e:
        logger.warning(f"Failed to extract PDF metadata from {pdf_path}: {e}")
        return {
            "title": "",
            "author": "",
            "subject": "",
            "creator": "",
            "producer": "",
            "creationDate": "",
            "modDate": "",
            "uid": "",
        }


def parse_pdf_date(date_str: str) -> str:
    """Convert PDF date format to ISO format.

    PDF format: D:YYYYMMDDHHmmss
    Output: YYYY-MM-DD

    Args:
        date_str: PDF date string

    Returns:
        ISO date string, or empty string if parsing fails
    """
    if not date_str or not date_str.startswith("D:"):
        return ""
    try:
        trimmed = date_str[2:16]
        return f"{trimmed[0:4]}-{trimmed[4:6]}-{trimmed[6:8]}"
    except (ValueError, IndexError):
        return ""
    
def generate_doc_id(
    doc: dict[str, Any],
    pdf_metadata: dict[str, Any],
    source_info: dict[str, Any],
) -> str:
    """Generate stable document ID.

    Priority:
    1. external_id from source_info
    2. uid from PDF metadata
    3. SHA-256 hash of title + author_org + first 1000 chars of first page

    Args:
        doc: TableAwareDocument dict
        pdf_metadata: Extracted PDF metadata
        source_info: Caller-supplied source info

    Returns:
        Stable document ID string
    """
    if source_info.get("external_id"):
        return str(source_info["external_id"])

    if pdf_metadata.get("uid"):
        return str(pdf_metadata["uid"])

    title = extract_title(doc, pdf_metadata, source_info)
    author_org = source_info.get("author_org", "")
    first_page_text = _get_page_text(doc, 0)[:1000]

    hash_input = f"{title}|{author_org}|{first_page_text}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


def extract_title(
    doc: dict[str, Any],
    pdf_metadata: dict[str, Any],
    source_info: dict[str, Any],
) -> str:
    """Extract or infer document title.

    Priority:
    1. PDF metadata title (if non-empty and not generic)
    2. Largest-font block on first page (if font_size > 18)
    3. Filename without extension

    Args:
        doc: TableAwareDocument dict
        pdf_metadata: Extracted PDF metadata
        source_info: Caller-supplied source info

    Returns:
        Title string
    """
    title = pdf_metadata.get("title", "").strip()
    if title and title.lower() not in {"untitled", "document", "document1"}:
        return title

    pages = doc.get("pages", [])
    if pages:
        first_page_blocks = pages[0].get("blocks", [])
        if first_page_blocks:
            largest_block = max(
                first_page_blocks,
                key=lambda b: b.get("font_size", 0),
            )
            if largest_block.get("font_size", 0) > 18:
                return largest_block["text"].strip()

    filename = os.path.basename(source_info["source_path"])
    return filename.replace(".pdf", "").replace("_", " ").title()

def generate_block_uid(
    doc_id: str,
    page_num: int,
    block_id: int,
    text: str,
) -> str:
    """Generate stable block UID based on content, not version.

    Allows unchanged blocks to keep the same UID across document versions,
    enabling deduplication when documents are updated. Intentionally excludes
    doc_version so unchanged content is not orphaned on document updates.

    Args:
        doc_id: Document ID
        page_num: 1-indexed page number
        block_id: Block ID within page
        text: Block text content

    Returns:
        16-character hex string
    """
    normalized_text = text.strip().lower()[:500]
    hash_input = f"{doc_id}|{page_num}|{block_id}|{normalized_text}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


def validate_metadata(doc: dict[str, Any]) -> bool:
    """Validate all required metadata is present and valid.

    Args:
        doc: MetadataDocument dict

    Returns:
        True if valid

    Raises:
        MetadataValidationError: If any required field is missing or invalid
    """
    if "doc_meta" not in doc:
        raise MetadataValidationError("Missing doc_meta")

    doc_meta = doc["doc_meta"]
    required_doc_fields = [
        "doc_id", "doc_version", "title", "source_name",
        "doc_type", "specialty", "source_path", "ingestion_date",
    ]
    for field in required_doc_fields:
        if field not in doc_meta:
            raise MetadataValidationError(f"Missing doc_meta.{field}")
        if not doc_meta[field]:
            raise MetadataValidationError(f"Empty doc_meta.{field}")

    for page in doc.get("pages", []):
        for block in page.get("blocks", []):
            required_block_fields = [
                "block_id", "block_uid", "page_number",
                "section_path", "section_title", "content_type",
                "include_in_chunks",
            ]
            for field in required_block_fields:
                if field not in block:
                    raise MetadataValidationError(f"Block missing {field}")
            if not isinstance(block["section_path"], list):
                raise MetadataValidationError("section_path must be list")
            if not isinstance(block["include_in_chunks"], bool):
                raise MetadataValidationError("include_in_chunks must be bool")

    return True

def _get_page_text(doc: dict[str, Any], page_index: int) -> str:
    """Get concatenated block text for a page by index.

    Args:
        doc: Document dict with pages list
        page_index: 0-based or negative index into pages list

    Returns:
        Concatenated block text, or empty string if page not found
    """
    pages = doc.get("pages", [])
    if not pages:
        return ""
    try:
        page = pages[page_index]
        return " ".join(b.get("text", "") for b in page.get("blocks", []))
    except IndexError:
        return ""
