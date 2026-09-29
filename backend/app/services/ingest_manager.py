"""Ingest manager: runs an ingestor, embeds chunks, stores them, updates SourceRecord.

This module owns the *lifecycle* of a source record. It deliberately owns no URL
classification of its own — every URL decision is delegated to
:mod:`app.core.url_safety`, which is the single authoritative path used by the
API layer too.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from app.core.errors import AppError
from app.core.url_safety import ParsedUrl, validate_ingest_url
from app.models.chunk import SourceType
from app.models.session import Session, SourceRecord
from app.services.embeddings import Embedder, get_embedder
from app.services.ingestion.base import IngestResult, detect_upload_type
from app.services.stores.session_store import SessionStore, get_session_store
from app.services.stores.vector_store import VectorStore, get_vector_store

logger = logging.getLogger(__name__)

# Strong references to in-flight background tasks.
#
# asyncio only holds a weak reference to a running task, so without this a task
# can be garbage-collected mid-execution and the source record would be stranded
# in status="processing" forever.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    """Schedule a background ingestion task and keep it alive until it finishes."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


def _fail(record: SourceRecord, exc: BaseException) -> None:
    """Move a record into the terminal failed state with a user-facing message."""
    if isinstance(exc, AppError):
        record.error = exc.message
    else:
        record.error = str(exc) or exc.__class__.__name__
    record.status = "failed"
    record.chunk_count = 0


async def _embed_and_store(
    session: Session,
    source_id: str,
    result: IngestResult,
    embedder: Embedder,
    vector_store: VectorStore,
    session_store: SessionStore,
    llm=None,
) -> None:
    """Embed chunks and persist them; update SourceRecord status."""
    record = session.sources[source_id]
    try:
        texts = [c.text for c in result.chunks]
        if not texts:
            raise AppError("NO_CONTENT", "No text could be extracted.", 422)

        embeddings = await embedder.embed(texts)
        vector_store.add(session.id, result.chunks, embeddings)

        record.status = "ready"
        record.chunk_count = len(result.chunks)
        record.warnings = result.warnings
        record.error = None

        # Generate summary + topics in the background (best-effort)
        try:
            from app.services.summarise import summarise_source
            summary, topics = await summarise_source(result.chunks, llm=llm)
            record.summary = summary or None
            record.topics = topics
        except Exception as exc:
            logger.warning("Summary generation failed for %s: %s", source_id, exc)
    except Exception as exc:
        logger.exception("Embedding failed for source %s", source_id)
        _fail(record, exc)


async def ingest_file(
    session_id: str,
    filename: str,
    data: bytes,
    *,
    content_type: str | None = None,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
    session_store: SessionStore | None = None,
    llm=None,
) -> str:
    """Ingest a PDF or PPTX file. Returns the new source_id.

    The upload is re-validated with the shared :func:`detect_upload_type` gate
    even though the API layer already checked it, so this function is safe to
    call directly. Ingestion runs in a background task; the source record is
    created immediately with status='processing'.
    """
    ss = session_store or get_session_store()
    vs = vector_store or get_vector_store()
    emb = embedder or get_embedder()

    # Raises UNSUPPORTED_FILE (415) for a bad extension, a mismatched declared
    # MIME type, or content that is not really a PDF/PPTX.
    source_type: SourceType = detect_upload_type(filename, content_type, data)

    session = ss.get(session_id)
    source_id = uuid.uuid4().hex

    record = SourceRecord(id=source_id, type=source_type, name=filename)
    session.sources[source_id] = record

    async def _run() -> None:
        try:
            if source_type == "pdf":
                from app.services.ingestion.pdf import ingest_pdf
                result: IngestResult = await asyncio.to_thread(
                    ingest_pdf, source_id, filename, data
                )
            else:
                from app.services.ingestion.pptx import ingest_pptx
                result = await asyncio.to_thread(ingest_pptx, source_id, filename, data)
        except Exception as exc:
            logger.exception("Ingestion failed for %s", filename)
            _fail(record, exc)
            return
        record.name = result.name  # ingestor may normalise the name
        await _embed_and_store(session, source_id, result, emb, vs, ss, llm=llm)

    _spawn(_run())
    return source_id


async def ingest_url(
    session_id: str,
    url: str,
    *,
    parsed_url: ParsedUrl | None = None,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
    session_store: SessionStore | None = None,
    llm=None,
) -> str:
    """Ingest a YouTube or web URL. Returns the new source_id.

    Classification and SSRF validation happen once, here, through the shared
    :mod:`app.core.url_safety` path — the same one the API layer uses. When
    ``parsed_url`` is already provided (i.e. the API layer already validated
    and classified the URL), it is used directly and :func:`validate_ingest_url`
    is **not** called again — preventing double DNS resolution and ensuring the
    classification cannot silently change between the two call sites.

    Runs in a background task.
    """
    ss = session_store or get_session_store()
    vs = vector_store or get_vector_store()
    emb = embedder or get_embedder()

    # Use the pre-validated ParsedUrl when available; only validate from scratch
    # when this function is called directly (e.g. in tests or future integrations).
    # Raises UNSAFE_URL (422) for a non-HTTP(S), credentialed, backslash-bearing
    # or private/loopback/link-local destination.
    parsed = parsed_url if parsed_url is not None else validate_ingest_url(url)

    session = ss.get(session_id)
    source_id = uuid.uuid4().hex

    record = SourceRecord(id=source_id, type=parsed.kind, name=parsed.normalized)
    session.sources[source_id] = record

    async def _run() -> None:
        try:
            if parsed.is_youtube:
                from app.services.ingestion.youtube import ingest_youtube
                result: IngestResult = await ingest_youtube(
                    source_id, parsed.normalized, parsed_url=parsed
                )
            else:
                from app.services.ingestion.web import ingest_web
                result = await ingest_web(source_id, parsed.normalized)
        except Exception as exc:
            logger.exception("URL ingestion failed for %s", parsed.normalized)
            _fail(record, exc)
            return
        record.name = result.name
        await _embed_and_store(session, source_id, result, emb, vs, ss, llm=llm)

    _spawn(_run())
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
        raise AppError("SOURCE_NOT_FOUND", f"Source {source_id!r} not found.", 404)

    del session.sources[source_id]
    vs.remove_source(session_id, source_id)
