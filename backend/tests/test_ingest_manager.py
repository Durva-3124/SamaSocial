"""Background source ingestion lifecycle tests."""
import asyncio
import socket

import fitz
import pytest

from app.core.errors import AppError
from app.models.chunk import Chunk, Locator
from app.services import ingest_manager
from app.services.ingestion.base import IngestResult
from app.services.stores.session_store import SessionStore
from app.services.stores.vector_store import VectorStore
from tests.fakes import FakeEmbedder


def _pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Enough readable text for successful ingestion.")
    data = document.tobytes()
    document.close()
    return data


async def _wait_for_new_ingestion_tasks(before: set[asyncio.Task]) -> None:
    tasks = ingest_manager._BACKGROUND_TASKS - before
    assert len(tasks) == 1, f"Expected 1 new task, found {len(tasks)}"
    await asyncio.gather(*tasks)


# ── file ingestion happy path ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_file_ingestion_transitions_to_ready_and_stores_chunks(monkeypatch):
    session_store = SessionStore(ttl_minutes=10)
    vector_store = VectorStore()
    session = session_store.create()

    async def no_summary(chunks, llm=None):
        return "summary", ["topic"]

    monkeypatch.setattr("app.services.summarise.summarise_source", no_summary)
    before = set(ingest_manager._BACKGROUND_TASKS)

    source_id = await ingest_manager.ingest_file(
        session.id,
        "lesson.pdf",
        _pdf_bytes(),
        content_type="application/pdf",
        embedder=FakeEmbedder(),
        vector_store=vector_store,
        session_store=session_store,
    )
    assert session.sources[source_id].status == "processing"

    await _wait_for_new_ingestion_tasks(before)

    source = session.sources[source_id]
    assert source.status == "ready"
    assert source.chunk_count > 0
    assert source.summary == "summary"
    assert source.topics == ["topic"]
    assert len(vector_store.all_chunks(session.id)) == source.chunk_count


@pytest.mark.asyncio
async def test_file_ingestion_source_name_updated_from_ingestor(monkeypatch):
    """The source record name is updated from the IngestResult.name after ingestion."""
    session_store = SessionStore(ttl_minutes=10)
    session = session_store.create()

    async def no_summary(chunks, llm=None):
        return None, []

    monkeypatch.setattr("app.services.summarise.summarise_source", no_summary)
    before = set(ingest_manager._BACKGROUND_TASKS)

    source_id = await ingest_manager.ingest_file(
        session.id,
        "my-lecture.pdf",
        _pdf_bytes(),
        content_type="application/pdf",
        embedder=FakeEmbedder(),
        vector_store=VectorStore(),
        session_store=session_store,
    )

    await _wait_for_new_ingestion_tasks(before)

    # The PDF ingestor returns filename unchanged as the name
    assert session.sources[source_id].name == "my-lecture.pdf"


# ── file ingestion failure ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_file_ingestion_transitions_to_failed_on_invalid_pdf(monkeypatch):
    session_store = SessionStore(ttl_minutes=10)
    vector_store = VectorStore()
    session = session_store.create()
    before = set(ingest_manager._BACKGROUND_TASKS)

    source_id = await ingest_manager.ingest_file(
        session.id,
        "broken.pdf",
        b"%PDF-this is not a parseable document",
        content_type="application/pdf",
        embedder=FakeEmbedder(),
        vector_store=vector_store,
        session_store=session_store,
    )
    assert session.sources[source_id].status == "processing"

    await _wait_for_new_ingestion_tasks(before)

    source = session.sources[source_id]
    assert source.status == "failed"
    assert source.error
    assert source.chunk_count == 0
    assert vector_store.all_chunks(session.id) == []


@pytest.mark.asyncio
async def test_file_ingestion_no_content_fails_gracefully(monkeypatch):
    """An empty file (0 bytes) must be caught at the detect_upload_type gate."""
    from app.services.ingestion.base import detect_upload_type

    with pytest.raises(AppError) as exc_info:
        detect_upload_type("empty.pdf", "application/pdf", b"")
    assert exc_info.value.code == "UNSUPPORTED_FILE"


# ── URL ingestion — classification passthrough ────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "source_type"),
    [
        ("https://example.com/article", "web"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
    ],
)
async def test_url_ingestion_reuses_validated_classification(monkeypatch, url, source_type):
    session_store = SessionStore(ttl_minutes=10)
    vector_store = VectorStore()
    session = session_store.create()
    parsed = ingest_manager.validate_ingest_url(url)
    chunk = Chunk(
        source_id="placeholder",
        source_type=source_type,
        text="A web article with enough useful content.",
        locator=Locator(heading="Article"),
    )

    async def fake_ingest(source_id, requested_url, **_kwargs):
        return IngestResult(
            name="Source",
            source_type=source_type,
            chunks=[chunk.model_copy(update={"source_id": source_id})],
        )

    async def no_summary(chunks, llm=None):
        return None, []

    monkeypatch.setattr(ingest_manager, "validate_ingest_url", lambda _: pytest.fail("reclassified URL"))
    monkeypatch.setattr("app.services.ingestion.web.ingest_web", fake_ingest)
    monkeypatch.setattr("app.services.ingestion.youtube.ingest_youtube", fake_ingest)
    monkeypatch.setattr("app.services.summarise.summarise_source", no_summary)
    before = set(ingest_manager._BACKGROUND_TASKS)

    source_id = await ingest_manager.ingest_url(
        session.id,
        parsed.normalized,
        parsed_url=parsed,
        embedder=FakeEmbedder(),
        vector_store=vector_store,
        session_store=session_store,
    )
    assert session.sources[source_id].type == source_type

    await _wait_for_new_ingestion_tasks(before)

    assert session.sources[source_id].status == "ready"
    assert vector_store.all_chunks(session.id)[0].source_id == source_id


@pytest.mark.asyncio
async def test_url_ingestion_validates_direct_service_calls(monkeypatch):
    session_store = SessionStore(ttl_minutes=10)
    session = session_store.create()
    validated = []
    parsed = ingest_manager.validate_ingest_url

    def record_validation(url):
        result = parsed(url)
        validated.append(url)
        return result

    monkeypatch.setattr(ingest_manager, "validate_ingest_url", record_validation)
    monkeypatch.setattr(
        "app.core.url_safety.socket.getaddrinfo",
        lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))],
    )
    monkeypatch.setattr(ingest_manager, "_spawn", lambda coroutine: coroutine.close())

    await ingest_manager.ingest_url(
        session.id,
        "https://example.com/article",
        embedder=FakeEmbedder(),
        vector_store=VectorStore(),
        session_store=session_store,
    )
    assert validated == ["https://example.com/article"]


# ── URL ingestion — failure modes ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_url_ingestion_failed_state_on_fetch_error(monkeypatch):
    """If the ingestor raises, the source record must land in status='failed'."""
    session_store = SessionStore(ttl_minutes=10)
    session = session_store.create()
    parsed = ingest_manager.validate_ingest_url("https://example.com")

    async def failing_ingest(source_id, url, **_kwargs):
        raise AppError("FETCH_FAILED", "Server returned 503.", 422)

    monkeypatch.setattr("app.services.ingestion.web.ingest_web", failing_ingest)
    before = set(ingest_manager._BACKGROUND_TASKS)

    source_id = await ingest_manager.ingest_url(
        session.id,
        parsed.normalized,
        parsed_url=parsed,
        embedder=FakeEmbedder(),
        vector_store=VectorStore(),
        session_store=session_store,
    )
    assert session.sources[source_id].status == "processing"

    await _wait_for_new_ingestion_tasks(before)

    source = session.sources[source_id]
    assert source.status == "failed"
    assert "503" in source.error or "Server returned" in source.error
    assert source.chunk_count == 0


@pytest.mark.asyncio
async def test_url_ingestion_failed_state_on_no_content(monkeypatch):
    """A source with no extractable content ends in 'failed' with a message."""
    session_store = SessionStore(ttl_minutes=10)
    session = session_store.create()
    parsed = ingest_manager.validate_ingest_url("https://example.com")

    async def empty_ingest(source_id, url, **_kwargs):
        raise AppError("NO_CONTENT", "Page had no readable text.", 422)

    monkeypatch.setattr("app.services.ingestion.web.ingest_web", empty_ingest)
    before = set(ingest_manager._BACKGROUND_TASKS)

    source_id = await ingest_manager.ingest_url(
        session.id,
        parsed.normalized,
        parsed_url=parsed,
        embedder=FakeEmbedder(),
        vector_store=VectorStore(),
        session_store=session_store,
    )

    await _wait_for_new_ingestion_tasks(before)

    source = session.sources[source_id]
    assert source.status == "failed"
    assert source.error == "Page had no readable text."


@pytest.mark.asyncio
async def test_url_ingestion_failed_state_on_unexpected_exception(monkeypatch):
    """Unexpected exceptions (not AppError) are caught and recorded on the record."""
    session_store = SessionStore(ttl_minutes=10)
    session = session_store.create()
    parsed = ingest_manager.validate_ingest_url("https://example.com")

    async def crash_ingest(source_id, url, **_kwargs):
        raise RuntimeError("Something unexpected broke")

    monkeypatch.setattr("app.services.ingestion.web.ingest_web", crash_ingest)
    before = set(ingest_manager._BACKGROUND_TASKS)

    source_id = await ingest_manager.ingest_url(
        session.id,
        parsed.normalized,
        parsed_url=parsed,
        embedder=FakeEmbedder(),
        vector_store=VectorStore(),
        session_store=session_store,
    )

    await _wait_for_new_ingestion_tasks(before)

    source = session.sources[source_id]
    assert source.status == "failed"
    assert source.error  # some error message must be present


# ── background task pinning ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_background_task_is_pinned_in_set(monkeypatch):
    """_BACKGROUND_TASKS must contain the task while it runs so GC cannot collect it."""
    session_store = SessionStore(ttl_minutes=10)
    session = session_store.create()
    parsed = ingest_manager.validate_ingest_url("https://example.com")

    barrier = asyncio.Event()
    task_ids_during_run: list[int] = []

    async def slow_ingest(source_id, url, **_kwargs):
        task_ids_during_run.append(len(ingest_manager._BACKGROUND_TASKS))
        await asyncio.sleep(0)  # yield so the set can be inspected
        raise AppError("NO_CONTENT", "test", 422)

    monkeypatch.setattr("app.services.ingestion.web.ingest_web", slow_ingest)
    before = set(ingest_manager._BACKGROUND_TASKS)

    source_id = await ingest_manager.ingest_url(
        session.id,
        parsed.normalized,
        parsed_url=parsed,
        embedder=FakeEmbedder(),
        vector_store=VectorStore(),
        session_store=session_store,
    )

    tasks_after_spawn = ingest_manager._BACKGROUND_TASKS - before
    assert len(tasks_after_spawn) == 1, "Task must be in _BACKGROUND_TASKS while it runs"

    await asyncio.gather(*tasks_after_spawn)

    # After completion the task is removed from the set
    assert not (ingest_manager._BACKGROUND_TASKS & tasks_after_spawn), (
        "Completed task must be removed from _BACKGROUND_TASKS"
    )


# ── remove_source ─────────────────────────────────────────────────────────────

def test_remove_source_deletes_record_and_chunks():
    session_store = SessionStore(ttl_minutes=10)
    vector_store = VectorStore()
    session = session_store.create()

    from app.models.session import SourceRecord
    session.sources["s1"] = SourceRecord(id="s1", type="web", name="x", status="ready")

    ingest_manager.remove_source(
        session.id, "s1", vector_store=vector_store, session_store=session_store
    )
    assert "s1" not in session.sources


def test_remove_source_not_found_raises_404():
    session_store = SessionStore(ttl_minutes=10)
    vector_store = VectorStore()
    session = session_store.create()

    with pytest.raises(AppError) as exc_info:
        ingest_manager.remove_source(
            session.id, "ghost", vector_store=vector_store, session_store=session_store
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "SOURCE_NOT_FOUND"
