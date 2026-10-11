"""PDF checks and text extraction (pdfplumber, MIT licence)."""
import io
import logging
from typing import Any

import pdfplumber

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
MAX_PAGES = 10
# Less text than this is treated as a scanned PDF (no text layer).
MIN_TEXT_CHARS = 200


class InvalidPdfError(Exception):
    """Damaged, encrypted, empty, or too many pages. The message is safe to show the user."""


class NotPdfError(InvalidPdfError):
    """The file isn't a PDF at all (checked by content, not by the browser's MIME type)."""


def page_count(data: bytes) -> int:
    """Check the upload is a readable PDF within the page limit; return its page count."""
    if not data.startswith(PDF_MAGIC):
        raise NotPdfError("Only PDF files are accepted.")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = len(pdf.pages)
    except Exception as error:  # pdfminer raises many unrelated types for damaged/encrypted files
        logger.info("Unreadable PDF: %s", type(error).__name__)
        raise InvalidPdfError("This PDF can't be opened. Try exporting it again.") from error
    if pages == 0:
        raise InvalidPdfError("This PDF has no pages.")
    if pages > MAX_PAGES:
        raise InvalidPdfError(f"Résumés can be at most {MAX_PAGES} pages.")
    return pages


def extract(data: bytes) -> dict[str, Any]:
    """Full text, text per page, and hyperlink targets (links are often not in the visible text)."""
    pages: list[str] = []
    links: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
            for link in page.hyperlinks:
                uri = link.get("uri")
                if uri and uri not in links:
                    links.append(uri)
    return {"full_text": "\n\n".join(pages).strip(), "pages": pages, "links": links}


def has_enough_text(extracted: dict[str, Any]) -> bool:
    return len(extracted["full_text"]) >= MIN_TEXT_CHARS
