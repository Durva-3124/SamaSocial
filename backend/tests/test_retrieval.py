"""Tests for Retriever — uses FakeEmbedder, no network."""
import numpy as np
import pytest

from app.models.chunk import Chunk, Locator
from app.services.retrieval import Retriever
from app.services.stores.vector_store import VectorStore
from tests.fakes import FakeEmbedder


def _chunk(text: str, source_id: str = "s1") -> Chunk:
    return Chunk(source_id=source_id, source_type="pdf", text=text, locator=Locator())


@pytest.fixture()
def store_with_chunks() -> tuple[VectorStore, list[Chunk]]:
    store = VectorStore()
    embedder = FakeEmbedder()
    chunks = [_chunk("python loops"), _chunk("machine learning basics", "s2")]

    import asyncio
    vecs = asyncio.run(embedder.embed([c.text for c in chunks]))
    store.add("sess", chunks, vecs)
    return store, chunks


@pytest.mark.asyncio
async def test_retriever_returns_above_threshold(store_with_chunks):
    store, chunks = store_with_chunks
    embedder = FakeEmbedder()
    retriever = Retriever(embedder=embedder, store=store)

    results = await retriever.retrieve("sess", "python loops", min_score=0.0)
    assert len(results) > 0
    assert all(score >= 0.0 for _, score in results)


@pytest.mark.asyncio
async def test_retriever_filters_below_threshold(store_with_chunks):
    store, _ = store_with_chunks
    embedder = FakeEmbedder()
    retriever = Retriever(embedder=embedder, store=store)

    results = await retriever.retrieve("sess", "python loops", min_score=2.0)
    assert results == []


@pytest.mark.asyncio
async def test_retriever_empty_session():
    retriever = Retriever(embedder=FakeEmbedder(), store=VectorStore())
    results = await retriever.retrieve("no_such_session", "anything", min_score=0.0)
    assert results == []


@pytest.mark.asyncio
async def test_retriever_source_id_filter(store_with_chunks):
    store, chunks = store_with_chunks
    embedder = FakeEmbedder()
    retriever = Retriever(embedder=embedder, store=store)

    results = await retriever.retrieve("sess", "python loops", source_ids=["s1"], min_score=0.0)
    assert all(c.source_id == "s1" for c, _ in results)
