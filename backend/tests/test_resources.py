"""Tests for resource enrichment — no real network."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import Response as HttpxResponse

from app.main import app
from app.models.course import Course, Lesson
from app.services.resources import (
    _url_reachable,
    _youtube_search,
    _tavily_search,
    enrich_lesson,
    enrich_course,
)
from app.services.stores.course_store import CourseStore
from tests.fakes import FakeLLM


def _minimal_course() -> Course:
    return Course.model_validate({
        "title": "Python Basics",
        "description": "Learn Python",
        "level": "beginner",
        "total_weeks": 1,
        "modules": [{
            "id": "m1", "title": "Intro",
            "lessons": [
                {"id": "m1-l1", "title": "Hello World", "duration_minutes": 30,
                 "objectives": [], "resources": []},
                {"id": "m1-l2", "title": "Variables", "duration_minutes": 30,
                 "objectives": [], "resources": []},
            ],
        }],
    })


def _mock_client(status: int = 200, json_body: dict | None = None):
    """Return a mock AsyncClient context manager that returns a fixed response."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_body or {}
    resp.raise_for_status = MagicMock(
        side_effect=None if status < 400 else Exception(f"HTTP {status}")
    )
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.head = AsyncMock(return_value=resp)
    client.get = AsyncMock(return_value=resp)
    client.post = AsyncMock(return_value=resp)
    return client


# ── URL validation ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_url_reachable_returns_true_on_200():
    with patch("app.services.resources.httpx.AsyncClient", return_value=_mock_client(200)):
        assert await _url_reachable("https://example.com") is True


@pytest.mark.asyncio
async def test_url_reachable_returns_false_on_404():
    with patch("app.services.resources.httpx.AsyncClient", return_value=_mock_client(404)):
        assert await _url_reachable("https://example.com/missing") is False


@pytest.mark.asyncio
async def test_url_reachable_returns_false_on_exception():
    client = _mock_client()
    client.head = AsyncMock(side_effect=Exception("timeout"))
    with patch("app.services.resources.httpx.AsyncClient", return_value=client):
        assert await _url_reachable("https://bad.example") is False


# ── YouTube search ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_youtube_search_returns_resources():
    yt_resp = {
        "items": [{"id": {"videoId": "abc123"}, "snippet": {"title": "Python Tutorial"}}]
    }
    with patch("app.services.resources.httpx.AsyncClient", return_value=_mock_client(200, yt_resp)):
        results = await _youtube_search("python loops", "fake_key")
    assert len(results) == 1
    assert results[0].type == "video"
    assert "abc123" in results[0].url
    assert results[0].validated is True


@pytest.mark.asyncio
async def test_youtube_search_returns_empty_on_error():
    client = _mock_client(403)
    client.get = AsyncMock(side_effect=Exception("403"))
    with patch("app.services.resources.httpx.AsyncClient", return_value=client):
        results = await _youtube_search("python", "bad_key")
    assert results == []


# ── Tavily search ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tavily_search_returns_resources():
    tv_resp = {"results": [{"url": "https://realpython.com/loops", "title": "Python Loops"}]}
    with patch("app.services.resources.httpx.AsyncClient", return_value=_mock_client(200, tv_resp)):
        results = await _tavily_search("python loops", "fake_key")
    assert len(results) == 1
    assert results[0].type == "article"
    assert results[0].validated is False


# ── enrich_lesson ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enrich_lesson_uses_llm_stub_when_no_keys():
    stub_payload = json.dumps({
        "resources": [
            {"title": "Python Docs", "url": "https://docs.python.org", "type": "article"},
        ]
    })
    llm = FakeLLM(script=[stub_payload])
    # HEAD returns 200 for validation
    with patch("app.services.resources.httpx.AsyncClient", return_value=_mock_client(200)):
        with patch("app.services.resources.get_settings") as ms:
            ms.return_value.YOUTUBE_API_KEY = None
            ms.return_value.TAVILY_API_KEY = None
            enriched = await enrich_lesson(Lesson(id="m1-l1", title="Hello World"), "Python", llm=llm)

    assert len(enriched.resources) == 1
    assert enriched.resources[0].validated is True


@pytest.mark.asyncio
async def test_enrich_lesson_drops_unreachable_urls():
    stub_payload = json.dumps({
        "resources": [
            {"title": "Bad Link", "url": "https://unreachable.example.com", "type": "article"},
        ]
    })
    llm = FakeLLM(script=[stub_payload])
    with patch("app.services.resources.httpx.AsyncClient", return_value=_mock_client(404)):
        with patch("app.services.resources.get_settings") as ms:
            ms.return_value.YOUTUBE_API_KEY = None
            ms.return_value.TAVILY_API_KEY = None
            enriched = await enrich_lesson(Lesson(id="m1-l1", title="Hello World"), "Python", llm=llm)

    assert enriched.resources == []


# ── enrich_course ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enrich_course_single_lesson():
    stub_payload = json.dumps({
        "resources": [
            {"title": "Python Docs", "url": "https://docs.python.org", "type": "article"},
        ]
    })
    llm = FakeLLM(script=[stub_payload])
    with patch("app.services.resources.httpx.AsyncClient", return_value=_mock_client(200)):
        with patch("app.services.resources.get_settings") as ms:
            ms.return_value.YOUTUBE_API_KEY = None
            ms.return_value.TAVILY_API_KEY = None
            updated, changed = await enrich_course(_minimal_course(), lesson_id="m1-l1", llm=llm)

    assert "m1-l1" in changed
    assert "m1-l2" not in changed
    assert len(updated.modules[0].lessons[0].resources) == 1


# ── refresh route ─────────────────────────────────────────────────────────────

def test_refresh_route_no_plan_returns_error_event():
    cs = CourseStore(ttl_minutes=10)
    record = cs.create()

    with patch("app.api.courses.get_course_store", return_value=cs):
        client = TestClient(app)
        resp = client.post(
            f"/api/courses/{record.id}/resources/refresh",
            json={"lesson_id": None},
        )

    assert resp.status_code == 200
    assert "NO_PLAN" in resp.text
