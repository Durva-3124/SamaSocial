"""Tests for session + source API endpoints — no network, no real embedder."""
import asyncio
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.stores.session_store import SessionStore
from app.services.stores.vector_store import VectorStore
from tests.fakes import FakeEmbedder

# ── helpers ───────────────────────────────────────────────────────────────────

_MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
    b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td (Hello world) Tj ET\nendstream\nendobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"xref\n0 6\n0000000000 65535 f\n"
    b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%EOF"
)


def _make_deps():
    """Return fresh store/embedder instances and the override dict."""
    ss = SessionStore(ttl_minutes=10)
    vs = VectorStore()
    emb = FakeEmbedder()
    return ss, vs, emb


# ── session lifecycle ─────────────────────────────────────────────────────────

def test_create_session():
    client = TestClient(app)
    resp = client.post("/api/sessions")
    assert resp.status_code == 201
    assert "session_id" in resp.json()


def test_list_sources_empty():
    client = TestClient(app)
    sid = client.post("/api/sessions").json()["session_id"]
    resp = client.get(f"/api/sessions/{sid}/sources")
    assert resp.status_code == 200
    assert resp.json() == {"sources": []}


def test_list_sources_unknown_session():
    client = TestClient(app)
    resp = client.get("/api/sessions/doesnotexist/sources")
    assert resp.status_code == 404


# ── file upload ───────────────────────────────────────────────────────────────

def test_upload_unsupported_type():
    client = TestClient(app)
    sid = client.post("/api/sessions").json()["session_id"]
    resp = client.post(
        f"/api/sessions/{sid}/sources/file",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNSUPPORTED_TYPE"


def test_upload_file_too_large(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "0")
    from app.core import config
    config.get_settings.cache_clear()

    client = TestClient(app)
    sid = client.post("/api/sessions").json()["session_id"]
    resp = client.post(
        f"/api/sessions/{sid}/sources/file",
        files={"file": ("doc.pdf", b"x" * 10, "application/pdf")},
    )
    assert resp.status_code == 413

    config.get_settings.cache_clear()


def test_upload_pdf_returns_202(monkeypatch):
    """202 is returned immediately; background task is patched to a no-op."""
    ss, vs, emb = _make_deps()

    async def _fake_ingest_file(sid, filename, data, **_):
        session = ss.get(sid)
        from app.models.session import SourceRecord
        src = SourceRecord(id="fakeid", type="pdf", name=filename, status="processing")
        session.sources["fakeid"] = src
        return "fakeid"

    with (
        patch("app.api.sessions.ingest_file", side_effect=_fake_ingest_file),
        patch("app.api.sessions.get_session_store", return_value=ss),
    ):
        client = TestClient(app)
        sid = client.post("/api/sessions").json()["session_id"]
        resp = client.post(
            f"/api/sessions/{sid}/sources/file",
            files={"file": ("slides.pdf", _MINIMAL_PDF, "application/pdf")},
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "processing"
    assert "source_id" in body


# ── URL ingestion ─────────────────────────────────────────────────────────────

def test_add_url_returns_202(monkeypatch):
    ss, vs, emb = _make_deps()

    async def _fake_ingest_url(sid, url, **_):
        session = ss.get(sid)
        from app.models.session import SourceRecord
        src = SourceRecord(id="urlid", type="web", name=url, status="processing")
        session.sources["urlid"] = src
        return "urlid"

    with (
        patch("app.api.sessions.ingest_url", side_effect=_fake_ingest_url),
        patch("app.api.sessions.get_session_store", return_value=ss),
    ):
        client = TestClient(app)
        sid = client.post("/api/sessions").json()["session_id"]
        resp = client.post(
            f"/api/sessions/{sid}/sources/url",
            json={"url": "https://example.com"},
        )
    assert resp.status_code == 202
    assert resp.json()["status"] == "processing"


# ── delete source ─────────────────────────────────────────────────────────────

def test_delete_source(monkeypatch):
    ss, vs, emb = _make_deps()

    with (
        patch("app.api.sessions.get_session_store", return_value=ss),
        patch("app.services.ingest_manager.get_session_store", return_value=ss),
        patch("app.services.ingest_manager.get_vector_store", return_value=vs),
    ):
        client = TestClient(app)
        sid = client.post("/api/sessions").json()["session_id"]

        # Manually plant a source record
        from app.models.session import SourceRecord
        session = ss.get(sid)
        session.sources["src1"] = SourceRecord(id="src1", type="web", name="x", status="ready")

        resp = client.delete(f"/api/sessions/{sid}/sources/src1")
        assert resp.status_code == 204

        sources = client.get(f"/api/sessions/{sid}/sources").json()["sources"]
        assert all(s["id"] != "src1" for s in sources)


def test_delete_source_not_found(monkeypatch):
    ss, _, _ = _make_deps()
    with patch("app.api.sessions.get_session_store", return_value=ss):
        client = TestClient(app)
        sid = client.post("/api/sessions").json()["session_id"]
        resp = client.delete(f"/api/sessions/{sid}/sources/ghost")
        assert resp.status_code == 404
