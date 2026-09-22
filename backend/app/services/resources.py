"""Resource enrichment: find real, validated links for each lesson.

The LLM never authors URLs.  Sources are YouTube Data API v3 and Tavily only.
If neither key is configured the caller receives a resources_unavailable signal.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.core.url_safety import validate_public_url
from app.core.errors import AppError
from app.models.course import Course, Lesson, Resource

logger = logging.getLogger(__name__)

_VALIDATE_TIMEOUT = 5.0
_SEARCH_TIMEOUT = 10.0

# Sentinel returned by enrich_lesson when no API keys are available.
RESOURCES_UNAVAILABLE = "RESOURCES_UNAVAILABLE"


# ── URL helpers ───────────────────────────────────────────────────────────────

def _is_http(url: str) -> bool:
    """Return True only for http/https URLs."""
    return urlparse(url).scheme in ("http", "https")


async def _url_reachable(url: str) -> bool:
    """HEAD-check a URL; re-validate the final URL after any redirects.

    Returns False for non-http/https, private/loopback targets, or errors.
    """
    if not _is_http(url):
        return False
    try:
        validate_public_url(url)
    except AppError:
        return False
    try:
        async with httpx.AsyncClient(
            timeout=_VALIDATE_TIMEOUT, follow_redirects=True
        ) as client:
            resp = await client.head(url)
            # Re-validate the final URL after redirects
            final = str(resp.url)
            if final != url:
                try:
                    validate_public_url(final)
                except AppError:
                    return False
            return resp.status_code < 400
    except Exception:
        return False


# ── YouTube Data API v3 ───────────────────────────────────────────────────────

async def _youtube_search(query: str, api_key: str) -> list[Resource]:
    """Search YouTube Data API v3; URLs are constructed from API-returned video IDs."""
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": 2,
        "key": api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=_SEARCH_TIMEOUT) as client:
            resp = await client.get(
                "https://www.googleapis.com/youtube/v3/search", params=params
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
    except Exception as exc:
        logger.warning("YouTube API search failed: %s", exc)
        return []

    resources: list[Resource] = []
    for item in items:
        vid_id = item.get("id", {}).get("videoId")
        title = item.get("snippet", {}).get("title", "Video")
        if vid_id:
            # URL is constructed from the API-returned video ID — not LLM-authored
            resources.append(Resource(
                title=title,
                url=f"https://www.youtube.com/watch?v={vid_id}",
                type="video",
                validated=True,
            ))
    return resources


# ── Tavily search ─────────────────────────────────────────────────────────────

async def _tavily_search(query: str, api_key: str) -> list[Resource]:
    """Search Tavily; accept only http/https URLs from the response."""
    payload = {"api_key": api_key, "query": query, "max_results": 2}
    try:
        async with httpx.AsyncClient(timeout=_SEARCH_TIMEOUT) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            results = resp.json().get("results", [])
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return []

    resources: list[Resource] = []
    for r in results:
        url = r.get("url", "")
        title = r.get("title", url)
        if url and _is_http(url):
            resources.append(Resource(
                title=title,
                url=url,
                type="article",
                validated=False,
            ))
    return resources


# ── validate and deduplicate ──────────────────────────────────────────────────

async def _validate_resources(resources: list[Resource]) -> list[Resource]:
    """HEAD-check unvalidated resources; drop unreachable or non-http/https ones."""
    validated: list[Resource] = []
    for r in resources:
        if not _is_http(r.url):
            logger.debug("Dropping non-http resource: %s", r.url)
            continue
        if r.validated:
            validated.append(r)
        elif await _url_reachable(r.url):
            validated.append(r.model_copy(update={"validated": True}))
        else:
            logger.debug("Dropping unreachable resource: %s", r.url)
    return validated


# ── public API ────────────────────────────────────────────────────────────────

async def enrich_lesson(
    lesson: Lesson,
    course_topic: str,
) -> Lesson | str:
    """Return an enriched Lesson, or RESOURCES_UNAVAILABLE if no API keys are set.

    The LLM is never called and never authors a URL.
    Strategy: YouTube API → Tavily → validate URLs.
    """
    settings = get_settings()
    query = f"{course_topic} {lesson.title}"

    if not settings.YOUTUBE_API_KEY and not settings.TAVILY_API_KEY:
        return RESOURCES_UNAVAILABLE

    resources: list[Resource] = []

    if settings.YOUTUBE_API_KEY:
        resources += await _youtube_search(query, settings.YOUTUBE_API_KEY)

    if len(resources) < 2 and settings.TAVILY_API_KEY:
        resources += await _tavily_search(query, settings.TAVILY_API_KEY)

    # Deduplicate by URL
    seen: set[str] = set()
    unique: list[Resource] = []
    for r in resources:
        if r.url not in seen:
            seen.add(r.url)
            unique.append(r)

    validated = await _validate_resources(unique[:4])
    return lesson.model_copy(update={"resources": validated})


async def enrich_course(
    course: Course,
    lesson_id: str | None = None,
) -> tuple[Course, list[str]] | str:
    """Enrich all lessons (or a single lesson) in the course.

    Returns (updated_course, list_of_changed_lesson_ids), or
    RESOURCES_UNAVAILABLE if no API keys are configured.
    """
    import json as _json

    settings = get_settings()
    if not settings.YOUTUBE_API_KEY and not settings.TAVILY_API_KEY:
        return RESOURCES_UNAVAILABLE

    data = _json.loads(course.model_dump_json())
    changed: list[str] = []

    for mod in data["modules"]:
        for lesson_data in mod["lessons"]:
            lid = lesson_data["id"]
            if lesson_id and lid != lesson_id:
                continue
            lesson_obj = Lesson.model_validate(lesson_data)
            result = await enrich_lesson(lesson_obj, course.title)
            if result is RESOURCES_UNAVAILABLE:
                return RESOURCES_UNAVAILABLE
            enriched: Lesson = result  # type: ignore[assignment]
            lesson_data["resources"] = [r.model_dump() for r in enriched.resources]
            if enriched.resources:
                changed.append(lid)

    return Course.model_validate(data), changed
