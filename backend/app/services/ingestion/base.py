"""Base types for all ingestors, plus the shared upload file-type gate."""
from __future__ import annotations

import io
import zipfile
from typing import Protocol

from pydantic import BaseModel

from app.core.errors import AppError
from app.models.chunk import Chunk, SourceType

__all__ = [
    "IngestResult",
    "Ingestor",
    "PDF_MIME_TYPES",
    "PPTX_MIME_TYPES",
    "SUPPORTED_EXTENSIONS",
    "describe_supported_types",
    "detect_upload_type",
    "sniff_file_type",
]


class IngestResult(BaseModel):
    """Output of any ingestor."""

    name: str
    source_type: SourceType
    chunks: list[Chunk]
    warnings: list[str] = []


class Ingestor(Protocol):
    """Synchronous ingestor interface (run in a thread via asyncio.to_thread)."""

    def ingest(self, *args, **kwargs) -> IngestResult: ...


# ── Upload file-type policy ───────────────────────────────────────────────────
#
# ONE place that decides whether an upload is an acceptable PDF or PPTX.
# The API layer, the ingest manager and the individual ingestors all defer to
# this, so extension, declared MIME type and actual magic bytes can never drift
# apart between them.

PDF_MIME_TYPES: frozenset[str] = frozenset({"application/pdf", "application/x-pdf"})

PPTX_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-powerpoint",
    }
)

#: Declared content types that carry no signal and must not be used to reject
#: or accept a file on their own. Browsers and curl frequently send these.
GENERIC_MIME_TYPES: frozenset[str] = frozenset(
    {
        "",
        "application/octet-stream",
        "binary/octet-stream",
        "application/force-download",
        "application/download",
    }
)

#: Maps the *lowercased* file extension to the source type it implies.
SUPPORTED_EXTENSIONS: dict[str, SourceType] = {
    "pdf": "pdf",
    "pptx": "pptx",
}

#: File extensions browsers may mistake for a supported upload.
_UNSUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {
        "doc", "docx", "xls", "xlsx", "ppt", "pptm", "odt", "odp", "ods", "rtf",
        "txt", "md", "csv", "json", "html", "htm", "xml", "png", "jpg", "jpeg",
        "gif", "webp", "svg", "zip", "gz", "tar", "exe", "dmg", "mp4", "mp3",
        "epub", "key", "numbers", "pages",
    }
)

_PDF_MAGIC = b"%PDF-"

_UNSUPPORTED_MESSAGE = "Only .pdf and .pptx files are supported."


def describe_supported_types() -> str:
    """Human-readable list of accepted uploads, for error messages and the UI."""
    return ", ".join(sorted(f".{ext}" for ext in SUPPORTED_EXTENSIONS))


def _unsupported(detail: str | None = None) -> AppError:
    message = _UNSUPPORTED_MESSAGE if detail is None else detail
    return AppError("UNSUPPORTED_FILE", message, 415)


def normalise_declared_mime(content_type: str | None) -> str:
    """Reduce a Content-Type header to its bare lowercase media type."""
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def sniff_file_type(data: bytes) -> SourceType | None:
    """Identify the real type of a file from its magic bytes.

    Returns ``"pdf"``, ``"pptx"`` or ``None`` when the bytes match neither.
    This deliberately does not raise so that callers can produce a 415 with a
    useful message.

    Handles truncated data gracefully: fewer than 4 bytes cannot match either
    supported format and return ``None`` instead of raising.
    """
    if not data or len(data) < 5:
        return None

    if data[:5] == _PDF_MAGIC:
        return "pdf"

    # OOXML packages are ZIP archives. Confirm the presentation part so a plain
    # .docx or .zip is not accepted as a PPTX.
    if data[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "ppt/presentation.xml" in archive.namelist():
                    return "pptx"
        except (zipfile.BadZipFile, OSError, ValueError):
            return None
        return None

    return None


def detect_upload_type(
    filename: str | None,
    content_type: str | None,
    data: bytes,
) -> SourceType:
    """Decide whether an upload is an acceptable PDF or PPTX.

    Checks, in order:

    1. the file extension is one of :data:`SUPPORTED_EXTENSIONS` (415 otherwise);
    2. if a meaningful ``Content-Type`` was declared, it agrees with the
       extension (415 on disagreement);
    3. the bytes actually are that type (415 otherwise).

    Size limiting is *not* done here — that is the API layer's job, and it must
    run before the file body is read into memory in full.

    Raises:
        AppError: ``UNSUPPORTED_FILE`` (415) for any failed check.
    """
    name = (filename or "").strip()
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if not extension or extension not in SUPPORTED_EXTENSIONS:
        hint = ""
        if extension in _UNSUPPORTED_EXTENSIONS:
            hint = f" .{extension} files are not supported."
        raise _unsupported(_UNSUPPORTED_MESSAGE + hint)

    expected = SUPPORTED_EXTENSIONS[extension]

    allowed_mimes = PDF_MIME_TYPES if expected == "pdf" else PPTX_MIME_TYPES
    declared = normalise_declared_mime(content_type)
    if declared not in GENERIC_MIME_TYPES and declared not in allowed_mimes:
        raise _unsupported(
            f"This file is {declared} but its name says .{extension}. "
            f"Upload a {'PDF' if expected == 'pdf' else 'PPTX'} file."
        )

    actual = sniff_file_type(data)
    if actual is None:
        raise _unsupported(
            f"The contents of this file are not a valid "
            f"{'PDF' if expected == 'pdf' else 'PPTX'}."
        )
    if actual != expected:
        raise _unsupported(
            f"The contents of this file are {actual.upper()}, "
            f"but its name says .{extension}."
        )

    return expected
