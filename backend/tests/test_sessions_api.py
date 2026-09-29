"""Tests for session + source API endpoints — no network, no real embedder."""
import asyncio
import io
import socket
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.errors import AppError
from app.api.sessions import upload_file
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


def _mock_dns(ip: str):
    return patch(
        "app.core.url_safety.socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 443))],
    )


def _minimal_pptx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ppt/presentation.xml", "<presentation/>")
    return buffer.getvalue()


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
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE"


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
    assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"

    config.get_settings.cache_clear()


def test_upload_pdf_rejects_mismatched_mime():
    client = TestClient(app)
    sid = client.post("/api/sessions").json()["session_id"]
    resp = client.post(
        f"/api/sessions/{sid}/sources/file",
        files={"file": ("notes.pdf", _MINIMAL_PDF, "application/vnd.ms-powerpoint")},
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE"


def test_upload_rejects_signature_extension_mismatch():
    client = TestClient(app)
    sid = client.post("/api/sessions").json()["session_id"]
    resp = client.post(
        f"/api/sessions/{sid}/sources/file",
        files={"file": ("notes.pptx", _MINIMAL_PDF, "application/octet-stream")},
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE"


def test_upload_truncated_data_returns_415():
    """A file with a valid extension but only 3 bytes cannot be sniffed."""
    client = TestClient(app)
    sid = client.post("/api/sessions").json()["session_id"]
    resp = client.post(
        f"/api/sessions/{sid}/sources/file",
        files={"file": ("doc.pdf", b"%PD", "application/pdf")},
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE"


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


def test_upload_pptx_returns_202():
    ss, _, _ = _make_deps()

    async def _fake_ingest_file(sid, filename, data, **_):
        session = ss.get(sid)
        from app.models.session import SourceRecord
        session.sources["pptxid"] = SourceRecord(
            id="pptxid", type="pptx", name=filename, status="processing"
        )
        return "pptxid"

    with (
        patch("app.api.sessions.ingest_file", side_effect=_fake_ingest_file),
        patch("app.api.sessions.get_session_store", return_value=ss),
    ):
        client = TestClient(app)
        sid = client.post("/api/sessions").json()["session_id"]
        resp = client.post(
            f"/api/sessions/{sid}/sources/file",
            files={"file": ("slides.pptx", _minimal_pptx(), "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
        )

    assert resp.status_code == 202
    assert resp.json()["source_id"] == "pptxid"


def test_upload_duplicate_file_rejected():
    """Uploading the same filename while it is still processing → 409 DUPLICATE_SOURCE."""
    ss, _, _ = _make_deps()

    async def _fake_ingest_file(sid, filename, data, **_):
        session = ss.get(sid)
        from app.models.session import SourceRecord
        session.sources["srcid"] = SourceRecord(
            id="srcid", type="pdf", name=filename, status="processing"
        )
        return "srcid"

    with (
        patch("app.api.sessions.ingest_file", side_effect=_fake_ingest_file),
        patch("app.api.sessions.get_session_store", return_value=ss),
    ):
        client = TestClient(app)
        sid = client.post("/api/sessions").json()["session_id"]
        # First upload succeeds
        resp1 = client.post(
            f"/api/sessions/{sid}/sources/file",
            files={"file": ("doc.pdf", _MINIMAL_PDF, "application/pdf")},
        )
        assert resp1.status_code == 202

        # Second upload of same file while still processing → 409
        resp2 = client.post(
            f"/api/sessions/{sid}/sources/file",
            files={"file": ("doc.pdf", _MINIMAL_PDF, "application/pdf")},
        )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "DUPLICATE_SOURCE"


def test_upload_too_many_sources():
    """Adding more than _MAX_SOURCES files → 400 TOO_MANY_SOURCES."""
    ss, _, _ = _make_deps()
    from app.models.session import SourceRecord

    call_count = [0]

    async def _fake_ingest_file(sid, filename, data, **_):
        call_count[0] += 1
        src_id = f"src{call_count[0]}"
        session = ss.get(sid)
        session.sources[src_id] = SourceRecord(
            id=src_id, type="pdf", name=filename, status="ready"
        )
        return src_id

    with (
        patch("app.api.sessions.ingest_file", side_effect=_fake_ingest_file),
        patch("app.api.sessions.get_session_store", return_value=ss),
    ):
        client = TestClient(app)
        sid = client.post("/api/sessions").json()["session_id"]

        # Add 8 distinct files (MAX_SOURCES = 8)
        for i in range(8):
            resp = client.post(
                f"/api/sessions/{sid}/sources/file",
                files={"file": (f"doc{i}.pdf", _MINIMAL_PDF, "application/pdf")},
            )
            assert resp.status_code == 202, f"Upload {i} should succeed"

        # 9th upload must fail
        resp = client.post(
            f"/api/sessions/{sid}/sources/file",
            files={"file": ("extra.pdf", _MINIMAL_PDF, "application/pdf")},
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TOO_MANY_SOURCES"


@pytest.mark.asyncio
async def test_upload_reads_only_one_byte_past_limit():
    class RecordingUpload:
        filename = "large.pdf"
        content_type = "application/pdf"

        def __init__(self):
            self.read_sizes = []

        async def read(self, size=-1):
            self.read_sizes.append(size)
            return b"x" * size

    ss, _, _ = _make_deps()
    session = ss.create()
    upload = RecordingUpload()

    with (
        patch("app.api.sessions.get_settings", return_value=SimpleNamespace(MAX_UPLOAD_MB=0)),
        patch("app.api.sessions.get_session_store", return_value=ss),
        pytest.raises(AppError) as exc_info,
    ):
        await upload_file(session.id, upload)

    assert exc_info.value.status_code == 413
    assert upload.read_sizes == [1]


# ── URL ingestion ─────────────────────────────────────────────────────────────

def test_add_url_returns_202(monkeypatch):
    ss, vs, emb = _make_deps()

    passed = {}

    async def _fake_ingest_url(sid, url, **kwargs):
        session = ss.get(sid)
        from app.models.session import SourceRecord
        passed.update(kwargs)
        src = SourceRecord(id="urlid", type="web", name=url, status="processing")
        session.sources["urlid"] = src
        return "urlid"

    with (
        patch("app.api.sessions.ingest_url", side_effect=_fake_ingest_url),
        patch("app.api.sessions.get_session_store", return_value=ss),
        _mock_dns("93.184.216.34"),
    ):
        client = TestClient(app)
        sid = client.post("/api/sessions").json()["session_id"]
        resp = client.post(
            f"/api/sessions/{sid}/sources/url",
            json={"url": "https://example.com"},
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "processing"
    assert body["type"] == "web"
    assert "source_id" in body
    assert passed["parsed_url"].kind == "web"


def test_add_youtube_url_returns_correct_type():
    ss, _, _ = _make_deps()

    async def _fake_ingest_url(sid, url, **kwargs):
        session = ss.get(sid)
        from app.models.session import SourceRecord
        src_type = kwargs["parsed_url"].kind
        session.sources["ytid"] = SourceRecord(id="ytid", type=src_type, name=url, status="processing")
        return "ytid"

    with (
        patch("app.api.sessions.ingest_url", side_effect=_fake_ingest_url),
        patch("app.api.sessions.get_session_store", return_value=ss),
    ):
        client = TestClient(app)
        sid = client.post("/api/sessions").json()["session_id"]
        resp = client.post(
            f"/api/sessions/{sid}/sources/url",
            json={"url": "https://youtu.be/dQw4w9WgXcQ"},
        )
    assert resp.status_code == 202
    assert resp.json()["type"] == "youtube"


def test_add_unsafe_url_returns_structured_422():
    client = TestClient(app)
    sid = client.post("/api/sessions").json()["session_id"]

    with _mock_dns("127.0.0.1"):
        resp = client.post(
            f"/api/sessions/{sid}/sources/url",
            json={"url": "https://example.com/"},
        )

    assert resp.status_code == 422
    assert resp.json() == {
        "error": {"code": "UNSAFE_URL", "message": "That URL is not allowed."}
    }


def test_add_url_rejects_non_http_schemes():
    client = TestClient(app)
    sid = client.post("/api/sessions").json()["session_id"]
    for url in ["ftp://example.com", "file:///etc/passwd", "javascript:alert(1)"]:
        resp = client.post(f"/api/sessions/{sid}/sources/url", json={"url": url})
        assert resp.status_code == 422, f"Expected 422 for {url!r}"
        assert resp.json()["error"]["code"] == "UNSAFE_URL"


def test_add_url_duplicate_rejected():
    """Adding the same URL twice → 409 DUPLICATE_SOURCE on the second attempt."""
    ss, _, _ = _make_deps()

    async def _fake_ingest_url(sid, url, **kwargs):
        session = ss.get(sid)
        from app.models.session import SourceRecord
        normalized = kwargs["parsed_url"].normalized
        session.sources["uid"] = SourceRecord(id="uid", type="web", name=normalized, status="processing")
        return "uid"

    with (
        patch("app.api.sessions.ingest_url", side_effect=_fake_ingest_url),
        patch("app.api.sessions.get_session_store", return_value=ss),
        _mock_dns("93.184.216.34"),
    ):
        client = TestClient(app)
        sid = client.post("/api/sessions").json()["session_id"]
        resp1 = client.post(f"/api/sessions/{sid}/sources/url", json={"url": "https://example.com"})
        assert resp1.status_code == 202

        resp2 = client.post(f"/api/sessions/{sid}/sources/url", json={"url": "https://example.com"})
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "DUPLICATE_SOURCE"


def test_add_url_missing_body_returns_422():
    client = TestClient(app)
    sid = client.post("/api/sessions").json()["session_id"]
    resp = client.post(f"/api/sessions/{sid}/sources/url", json={})
    assert resp.status_code == 422


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


# ── spoofing / classification ─────────────────────────────────────────────────

def test_ingest_url_spoofed_youtube_routes_to_web():
    """Spoofed YouTube URLs must create a 'web' source record, not 'youtube'."""
    ss, vs, emb = _make_deps()

    captured: list[dict] = []

    async def _fake_ingest_url(sid, url, **kwargs):
        session = ss.get(sid)
        from app.models.session import SourceRecord
        src_type = kwargs["parsed_url"].kind
        captured.append({"url": url, "type": src_type})
        src = SourceRecord(id="fakeid", type=src_type, name=url, status="processing")
        session.sources["fakeid"] = src
        return "fakeid"

    spoofed_urls = [
        "https://youtube.com.evil.com/watch?v=abc",
        "https://evil.example/youtu.be/abc",
    ]
    for url in spoofed_urls:
        captured.clear()
        with (
            patch("app.api.sessions.ingest_url", side_effect=_fake_ingest_url),
            patch("app.api.sessions.get_session_store", return_value=ss),
            _mock_dns("93.184.216.34"),
        ):
            client = TestClient(app)
            sid = client.post("/api/sessions").json()["session_id"]
            resp = client.post(
                f"/api/sessions/{sid}/sources/url",
                json={"url": url},
            )
        assert resp.status_code == 202
        assert captured[0]["type"] == "web", (
            f"Expected 'web' for {url!r}, got {captured[0]['type']!r}"
        )


# ── accepted file types endpoint ──────────────────────────────────────────────

def test_accepted_file_types_endpoint():
    client = TestClient(app)
    resp = client.get("/api/sources/accept")
    assert resp.status_code == 200
    body = resp.json()
    assert "pdf" in body["extensions"]
    assert "pptx" in body["extensions"]
    assert ".pdf" in body["accept"]
    assert ".pptx" in body["accept"]
