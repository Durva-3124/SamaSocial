"""Background source ingestion lifecycle tests."""
import asyncio
import socket

import fitz
import pytest

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
    assert len(tasks) == 1
    await asyncio.gather(*tasks)


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