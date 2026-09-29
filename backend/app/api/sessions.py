"""Session and source management routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Response, UploadFile
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.url_safety import validate_ingest_url
from app.services.ingest_manager import ingest_file, ingest_url, remove_source
from app.services.ingestion.base import describe_supported_types, detect_upload_type
from app.services.stores.session_store import get_session_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_MAX_SOURCES = 8


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.post("/sessions", status_code=201)
async def create_session() -> dict:
    """Create a new learning session."""
    session = get_session_store().create()
    return {"session_id": session.id}


# ── Sources ───────────────────────────────────────────────────────────────────

@router.post("/sessions/{sid}/sources/file", status_code=202)
async def upload_file(sid: str, file: UploadFile) -> dict:
    """Ingest a PDF or PPTX file into the session.

    Returns 202 immediately; parsing and embedding continue in the background.
    Rejects unsupported media with 415 and oversized uploads with 413 *before*
    any ingestion work is scheduled.
    """
    settings = get_settings()
    filename = file.filename or "upload"

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise AppError(
            "FILE_TOO_LARGE",
            f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit.",
            413,
        )

    # Single authoritative gate: extension + declared MIME + magic bytes.
    # Raises AppError("UNSUPPORTED_FILE", 415) on any mismatch.
    detect_upload_type(filename, file.content_type, data)

    session = get_session_store().get(sid)
    if len(session.sources) >= _MAX_SOURCES:
        raise AppError("TOO_MANY_SOURCES", f"Sessions are limited to {_MAX_SOURCES} sources.", 400)

    # Duplicate detection: same filename + same size
    for src in session.sources.values():
        if src.name == filename and src.chunk_count == 0 and src.status == "processing":
            raise AppError("DUPLICATE_SOURCE", "This file is already being processed.", 409)

    source_id = await ingest_file(sid, filename, data, content_type=file.content_type)
    return {"source_id": source_id, "status": "processing"}


class UrlBody(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


@router.post("/sessions/{sid}/sources/url", status_code=202)
async def add_url(sid: str, body: UrlBody) -> dict:
    """Ingest a YouTube video or webpage URL into the session.

    The URL is classified and safety-checked synchronously through
    :mod:`app.core.url_safety`, so unsafe input fails fast with 422 rather than
    silently becoming a failed background source.
    """
    session = get_session_store().get(sid)

    # Raises AppError("UNSAFE_URL", 422) for a non-HTTP(S) scheme, a
    # backslash/control-character smuggling attempt, embedded credentials, or a
    # hostname that resolves to loopback/private/link-local/reserved space.
    parsed = validate_ingest_url(body.url)

    if len(session.sources) >= _MAX_SOURCES:
        raise AppError("TOO_MANY_SOURCES", f"Sessions are limited to {_MAX_SOURCES} sources.", 400)

    # Duplicate detection, against both the raw and the normalised form.
    for src in session.sources.values():
        if src.name in (body.url, parsed.normalized):
            raise AppError("DUPLICATE_SOURCE", "This URL has already been added.", 409)

    source_id = await ingest_url(sid, parsed.normalized, parsed_url=parsed)
    return {"source_id": source_id, "status": "processing", "type": parsed.kind}


@router.get("/sessions/{sid}/sources")
async def list_sources(sid: str) -> dict:
    """List all sources in a session."""
    session = get_session_store().get(sid)
    return {
        "sources": [
            {
                "id": s.id,
                "type": s.type,
                "name": s.name,
                "status": s.status,
                "error": s.error,
                "chunk_count": s.chunk_count,
                "summary": s.summary,
                "topics": s.topics,
                "warnings": s.warnings,
            }
            for s in session.sources.values()
        ]
    }


@router.delete("/sessions/{sid}/sources/{source_id}", status_code=204)
async def delete_source(sid: str, source_id: str) -> Response:
    """Remove a source and its chunks from the session."""
    remove_source(sid, source_id)
    return Response(status_code=204)


@router.get("/sources/accept")
async def accepted_file_types() -> dict:
    """Report which upload types the backend accepts, for the file picker."""
    return {
        "extensions": ["pdf", "pptx"],
        "accept": ".pdf,.pptx",
        "description": f"Supported: {describe_supported_types()}",
    }
