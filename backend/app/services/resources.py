"""Resource enrichment: find real, validated links for each lesson."""
import logging
import uuid

import httpx

from app.core.config import get_settings
from app.models.course import Course, Lesson, Resource
from app.models.llm import Message
from app.services.llm import LLMClient, get_llm

logger = logging.getLogger(__name__)

_VALIDATE_TIMEOUT = 5.0
_SEARCH_TIMEOUT = 10.0


# ── URL validation ────────────────────────────────────────────────────────────

async def _url_reachable(url: str) -> bool:
    """Return True if the URL responds with a non-error status (HEAD request)."""
    try:
        async with httpx.AsyncClient(timeout=_VALIDATE_TIMEOUT, follow_redirects=True) as client:
            resp = await client.head(url)
            return resp.status_code < 400
    except Exception:
        return False


# ── YouTube Data API v3 ───────────────────────────────────────────────────────

async def _youtube_search(query: str, api_key: str) -> list[Resource]:
    """Search YouTube Data API v3 for videos matching query."""
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
            resources.append(Resource(
                title=title,
                url=f"https://www.youtube.com/watch?v={vid_id}",
                type="video",
                validated=True,
            ))
    return resources


# ── Tavily search ─────────────────────────────────────────────────────────────

async def _tavily_search(query: str, api_key: str) -> list[Resource]:
    """Search Tavily for articles matching query."""
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
        if url:
            resources.append(Resource(
                title=title,
                url=url,
                type="article",
                validated=False,
            ))
    return resources


# ── LLM stub fallback ─────────────────────────────────────────────────────────

async def _llm_stub_resources(lesson_title: str, course_topic: str, llm: LLMClient) -> list[Resource]:
    """Ask the LLM to suggest resource titles (no real URLs — marked unvalidated)."""
    from pydantic import BaseModel

    class _Stub(BaseModel):
        resources: list[dict]

    system = (
        "Suggest 2 learning resources for the given lesson. "
        "Return JSON: {\"resources\": [{\"title\": str, \"url\": str, \"type\": \"video|article\"}]}. "
        "Use real, well-known URLs where possible (e.g. youtube.com, docs.python.org)."
    )
    msgs = [Message(role="user", content=f"Course: {course_topic}\nLesson: {lesson_title}")]
    try:
        result = await llm.complete_json(msgs, system=system, schema=_Stub)
        return [
            Resource(
                title=r.get("title", "Resource"),
                url=r.get("url", "https://example.com"),
                type=r.get("type", "article"),
                validated=False,
            )
            for r in result.resources[:2]
        ]
    except Exception as exc:
        logger.warning("LLM stub resources failed: %s", exc)
        return []


# ── validate and deduplicate ──────────────────────────────────────────────────

async def _validate_resources(resources: list[Resource]) -> list[Resource]:
    """HEAD-check unvalidated resources; drop unreachable ones."""
    validated: list[Resource] = []
    for r in resources:
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
    *,
    llm: LLMClient | None = None,
) -> Lesson:
    """Return a copy of the lesson with resources populated.

    Strategy: YouTube API → Tavily → LLM stubs → validate URLs.
    Gracefully degrades if keys are missing.
    """
    settings = get_settings()
    _llm = llm or get_llm()
    query = f"{course_topic} {lesson.title}"

    resources: list[Resource] = []

    if settings.YOUTUBE_API_KEY:
        resources += await _youtube_search(query, settings.YOUTUBE_API_KEY)

    if len(resources) < 2 and settings.TAVILY_API_KEY:
        resources += await _tavily_search(query, settings.TAVILY_API_KEY)

    if len(resources) < 2:
        resources += await _llm_stub_resources(lesson.title, course_topic, _llm)

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
    *,
    llm: LLMClient | None = None,
) -> tuple[Course, list[str]]:
    """Enrich all lessons (or a single lesson) in the course.

    Returns (updated_course, list_of_changed_lesson_ids).
    """
    import json as _json
    data = _json.loads(course.model_dump_json())
    changed: list[str] = []

    for mod in data["modules"]:
        for lesson_data in mod["lessons"]:
            lid = lesson_data["id"]
            if lesson_id and lid != lesson_id:
                continue
            lesson_obj = Lesson.model_validate(lesson_data)
            enriched = await enrich_lesson(lesson_obj, course.title, llm=llm)
            lesson_data["resources"] = [r.model_dump() for r in enriched.resources]
            if enriched.resources:
                changed.append(lid)

    return Course.model_validate(data), changed
