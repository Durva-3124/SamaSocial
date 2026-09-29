"""PDF ingestion using PyMuPDF (fitz)."""
import logging

import fitz  # PyMuPDF

from app.core.errors import AppError
from app.models.chunk import Chunk, Locator
from app.services.chunking import split_text
from app.services.ingestion.base import IngestResult

logger = logging.getLogger(__name__)

_MIN_TEXT_CHARS = 10
_BLANK_PAGE_THRESHOLD = 0.30


def extract_pdf_pages(data: bytes) -> tuple[int, list[tuple[int, str]]]:
    """Open the PDF once and return (total_pages, [(1-based page number, text)]).

    Skips blank/image-only pages. Reused by the syllabus feature.

    Raises:
        AppError: ``INVALID_PDF`` (422) when the bytes are not a valid PDF.
    """
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise AppError("INVALID_PDF", "The file is not a valid PDF.", 422) from exc

    total_pages = len(doc)
    pages: list[tuple[int, str]] = []
    try:
        for i, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if text:
                pages.append((i, text))
    finally:
        doc.close()

    return total_pages, pages


def ingest_pdf(source_id: str, filename: str, data: bytes) -> IngestResult:
    """Ingest a PDF file into chunks with page locators."""
    total_pages, pages = extract_pdf_pages(data)

    total_text = " ".join(t for _, t in pages)
    if len(total_text) < _MIN_TEXT_CHARS:
        raise AppError(
            "NO_TEXT_LAYER",
            "This PDF looks scanned or image-only, so no text could be extracted.",
            422,
        )

    warnings: list[str] = []
    blank_count = total_pages - len(pages)
    if total_pages > 0 and blank_count / total_pages > _BLANK_PAGE_THRESHOLD:
        warnings.append(
            f"{blank_count} of {total_pages} pages are blank or image-only."
        )

    chunks: list[Chunk] = []
    for page_num, text in pages:
        for piece in split_text(text):
            chunks.append(
                Chunk(
                    source_id=source_id,
                    source_type="pdf",
                    text=piece,
                    locator=Locator(page=page_num),
                )
            )

    return IngestResult(
        name=filename,
        source_type="pdf",
        chunks=chunks,
        warnings=warnings,
    )
