"""Tests for SessionStore and VectorStore — no network, no real embedder."""
import time

import numpy as np
import pytest

from app.core.errors import AppError
from app.models.chunk import Chunk, Locator
from app.services.stores.session_store import SessionStore
from app.services.stores.vector_store import VectorStore


# ── SessionStore ──────────────────────────────────────────────────────────────

def test_session_create_and_get():
    store = SessionStore(ttl_minutes=10)
    session = store.create()
    fetched = store.get(session.id)
    assert fetched.id == session.id


def test_session_not_found_raises():
    store = SessionStore(ttl_minutes=10)
    with pytest.raises(AppError) as exc_info:
        store.get("nonexistent")
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "SESSION_NOT_FOUND"


def test_session_delete_is_idempotent():
    store = SessionStore(ttl_minutes=10)
    session = store.create()
    store.delete(session.id)
    store.delete(session.id)  # second delete must not raise
    with pytest.raises(AppError):
        store.get(session.id)


def test_session_ttl_eviction():
    store = SessionStore(ttl_minutes=0)  # TTL = 0 → expires immediately
    session = store.create()
    # Force last_active into the past
    from datetime import UTC, datetime, timedelta
    store._sessions[session.id].last_active = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(AppError):
        store.get(session.id)


# ── VectorStore ───────────────────────────────────────────────────────────────

def _make_chunk(source_id: str = "s1") -> Chunk:
    return Chunk(source_id=source_id, source_type="pdf", text="hello", locator=Locator())


def _unit_vec(dim: int, idx: int) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[idx] = 1.0
    return v


def test_vector_store_add_and_query():
    store = VectorStore()
    chunk = _make_chunk()
    vec = _unit_vec(4, 0).reshape(1, 4)
    store.add("sess1", [chunk], vec)

    results = store.query("sess1", _unit_vec(4, 0), top_k=1)
    assert len(results) == 1
    assert results[0][0].id == chunk.id
    assert pytest.approx(results[0][1], abs=1e-5) == 1.0


def test_vector_store_empty_session_returns_empty():
    store = VectorStore()
    assert store.query("missing", _unit_vec(4, 0), top_k=5) == []


def test_vector_store_remove_source():
    store = VectorStore()
    c1 = _make_chunk("src_a")
    c2 = _make_chunk("src_b")
    vecs = np.stack([_unit_vec(4, 0), _unit_vec(4, 1)])
    store.add("sess2", [c1, c2], vecs)

    store.remove_source("sess2", "src_a")
    results = store.query("sess2", _unit_vec(4, 0), top_k=5)
    ids = [r[0].source_id for r in results]
    assert "src_a" not in ids
    assert "src_b" in ids


def test_vector_store_filter_by_source_ids():
    store = VectorStore()
    c1 = _make_chunk("src_a")
    c2 = _make_chunk("src_b")
    vecs = np.stack([_unit_vec(4, 0), _unit_vec(4, 0)])  # same direction
    store.add("sess3", [c1, c2], vecs)

    results = store.query("sess3", _unit_vec(4, 0), top_k=5, source_ids=["src_a"])
    assert all(r[0].source_id == "src_a" for r in results)


def test_vector_store_accumulates_across_adds():
    store = VectorStore()
    c1 = _make_chunk("src_a")
    c2 = _make_chunk("src_b")
    store.add("sess4", [c1], _unit_vec(4, 0).reshape(1, 4))
    store.add("sess4", [c2], _unit_vec(4, 1).reshape(1, 4))

    results = store.query("sess4", _unit_vec(4, 0), top_k=5)
    assert len(results) == 2
