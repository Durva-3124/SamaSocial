"""Ingest manager: runs an ingestor, embeds chunks, stores them, updates SourceRecord."""
import asyncio
import logging
import uuid

from app.models.session import Session, SourceRecord
from app.services.embeddings import Embedder, get_embedder
from app.services.ingestion.base import IngestResult
from app.services.stores.session_store import SessionStore, get_session_store
from app.services.stores.vector_store import VectorStore, get_vector_store

logger = logging.getLogger(__name__)


async def _embed_and_store(
    session: Session,
    source_id: str,
    result: IngestResult,
    embedder: Embedder,
    vector_store: VectorStore,
    session_store: SessionStore,
) -> None:
    """Embed chunks and persist them; update SourceRecord status."""
    record = session.sources[source_id]
    try:
        texts = [c.text for c in result.chunks]
        embeddings = await embedder.embed(texts)
        vector_store.add(session.id, result.chunks, embeddings)

        record.status = "ready"
        record.chunk_count = len(result.chunks)
        record.warnings = result.warnings
    except Exception as exc:
        logger.exception("Embedding failed for source %s", source_id)
        record.status = "failed"
        record.error = str(exc)


async def ingest_file(
    session_id: str,
    filename: str,
    data: bytes,
    *,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
    session_store: SessionStore | None = None,
) -> str:
    """Ingest a PDF or PPTX file. Returns the new source_id.

    Ingestion runs in a background task; the source record is created
    immediately with status='processing'.
    """
    ss = session_store or get_session_store()
    vs = vector_store or get_vector_store()
    emb = embedder or get_embedder()

    session = ss.get(session_id)
    source_id = uuid.uuid4().hex
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    source_type = "pdf" if ext == "pdf" else "pptx"

    record = SourceRecord(id=source_id, type=source_type, name=filename)
    session.sources[source_id] = record

    async def _run() -> None:
        try:
            if source_type == "pdf":
                from app.services.ingestion.pdf import ingest_pdf
                result: IngestResult = await asyncio.to_thread(ingest_pdf, source_id, filename, data)
            else:
                from app.services.ingestion.pptx import ingest_pptx
                result = await asyncio.to_thread(ingest_pptx, source_id, filename, data)
        except Exception as exc:
            logger.exception("Ingestion failed for %s", filename)
            record.status = "failed"
            record.error = str(exc)
            return
        await _embed_and_store(session, source_id, result, emb, vs, ss)
        record.name = result.name  # ingestor may normalise the name

    asyncio.create_task(_run())
    return source_id


async def ingest_url(
    session_id: str,
    url: str,
    *,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
    session_store: SessionStore | None = None,
) -> str:
    """Ingest a YouTube or web URL. Returns the new source_id.

    Auto-detects YouTube vs. webpage. Runs in a background task.
    """
    ss = session_store or get_session_store()
    vs = vector_store or get_vector_store()
    emb = embedder or get_embedder()

    session = ss.get(session_id)
    source_id = uuid.uuid4().hex

    is_youtube = "youtube.com" in url or "youtu.be" in url
    source_type = "youtube" if is_youtube else "web"

    record = SourceRecord(id=source_id, type=source_type, name=url)
    session.sources[source_id] = record

    async def _run() -> None:
        try:
            if is_youtube:
                from app.services.ingestion.youtube import ingest_youtube
                result: IngestResult = await ingest_youtube(source_id, url)
            else:
                from app.services.ingestion.web import ingest_web
                result = await ingest_web(source_id, url)
        except Exception as exc:
            logger.exception("URL ingestion failed for %s", url)
            record.status = "failed"
            record.error = str(exc)
            return
        await _embed_and_store(session, source_id, result, emb, vs, ss)
        record.name = result.name

    asyncio.create_task(_run())
    return source_id


def remove_source(
    session_id: str,
    source_id: str,
    *,
    vector_store: VectorStore | None = None,
    session_store: SessionStore | None = None,
) -> None:
    """Remove a source record and its chunks from the session."""
    ss = session_store or get_session_store()
    vs = vector_store or get_vector_store()

    session = ss.get(session_id)
    if source_id not in session.sources:
        from app.core.errors import AppError
        raise AppError("SOURCE_NOT_FOUND", f"Source {source_id!r} not found.", 404)

    del session.sources[source_id]
    vs.remove_source(session_id, source_id)
