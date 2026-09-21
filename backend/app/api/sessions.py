"""Session and source management routes."""
import logging

from fastapi import APIRouter, Response, UploadFile
from pydantic import BaseModel, HttpUrl

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.ingest_manager import ingest_file, ingest_url, remove_source
from app.services.stores.session_store import get_session_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.post("/sessions", status_code=201)
async def create_session() -> dict:
    """Create a new learning session."""
    session = get_session_store().create()
    return {"session_id": session.id}


# ── Sources ───────────────────────────────────────────────────────────────────

@router.post("/sessions/{sid}/sources/file", status_code=202)
async def upload_file(sid: str, file: UploadFile) -> dict:
    """Ingest a PDF or PPTX file into the session."""
    settings = get_settings()
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("pdf", "pptx"):
        raise AppError("UNSUPPORTED_TYPE", "Only .pdf and .pptx files are supported.", 422)

    data = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise AppError(
            "FILE_TOO_LARGE",
            f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit.",
            413,
        )

    source_id = await ingest_file(sid, filename, data)
    return {"source_id": source_id, "status": "processing"}


class UrlBody(BaseModel):
    url: str


@router.post("/sessions/{sid}/sources/url", status_code=202)
async def add_url(sid: str, body: UrlBody) -> dict:
    """Ingest a YouTube video or webpage URL into the session."""
    source_id = await ingest_url(sid, body.url)
    return {"source_id": source_id, "status": "processing"}


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
            }
            for s in session.sources.values()
        ]
    }


@router.delete("/sessions/{sid}/sources/{source_id}", status_code=204)
async def delete_source(sid: str, source_id: str) -> Response:
    """Remove a source and its chunks from the session."""
    remove_source(sid, source_id)
    return Response(status_code=204)
