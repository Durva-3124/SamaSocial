"""Course planner API routes."""
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.sse import sse as _sse
from app.models.course import missing_intake_fields
from app.services.course_chat import course_chat_stream
from app.services.plan_ops import apply_patch
from app.services.stores.course_store import get_course_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/courses", status_code=201)
async def create_course() -> dict:
    """Create a new course planning session."""
    record = get_course_store().create()
    return {"course_id": record.id}


@router.get("/courses/{cid}")
async def get_course(cid: str) -> dict:
    """Return the full state of a course planning session."""
    record = get_course_store().get(cid)
    missing = missing_intake_fields(record.intake)
    return {
        "intake": record.intake.model_dump(),
        "missing": missing,
        "plan": record.plan.model_dump() if record.plan else None,
        "plan_version": record.plan_version,
        "messages": [m.model_dump() for m in record.messages],
    }


class ChatBody(BaseModel):
    message: str


@router.post("/courses/{cid}/chat")
async def course_chat(cid: str, body: ChatBody) -> StreamingResponse:
    """Stream a course planning chat turn as SSE."""
    record = get_course_store().get(cid)
    return StreamingResponse(
        course_chat_stream(record, body.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class PatchBody(BaseModel):
    path: str
    value: object


@router.patch("/courses/{cid}/plan")
async def patch_plan(cid: str, body: PatchBody) -> dict:
    """Apply a JSON Pointer patch to the course plan."""
    record = get_course_store().get(cid)
    if record.plan is None:
        raise AppError("NO_PLAN", "No plan exists yet for this course.", 400)
    async with record.lock:
        record.plan = apply_patch(record.plan, body.path, body.value)
        record.plan_version += 1
    return {"plan": record.plan.model_dump(), "plan_version": record.plan_version}


class RefreshBody(BaseModel):
    lesson_id: str | None = None


async def _refresh_stream(cid: str, lesson_id: str | None) -> AsyncIterator[str]:
    """SSE generator for resource refresh."""
    from app.services.resources import enrich_course, RESOURCES_UNAVAILABLE
    record = get_course_store().get(cid)
    if record.plan is None:
        yield _sse("error", {"code": "NO_PLAN", "message": "No plan to enrich."})
        return
    try:
        result = await enrich_course(record.plan, lesson_id)
    except Exception as exc:
        logger.exception("Resource refresh failed")
        yield _sse("error", {"code": "REFRESH_ERROR", "message": str(exc)})
        return
    if result is RESOURCES_UNAVAILABLE:
        yield _sse("resources_unavailable", {
            "reason": "No YOUTUBE_API_KEY or TAVILY_API_KEY configured."
        })
        yield _sse("done", {})
        return
    updated_plan, changed_ids = result
    record.plan = updated_plan
    record.plan_version += 1
    yield _sse("plan_update", {
        "plan": updated_plan.model_dump(),
        "plan_version": record.plan_version,
        "changed_ids": changed_ids,
    })
    yield _sse("done", {})


@router.post("/courses/{cid}/resources/refresh")
async def refresh_resources(cid: str, body: RefreshBody) -> StreamingResponse:
    """Enrich lesson resources via YouTube/Tavily/LLM and stream plan_update."""
    return StreamingResponse(
        _refresh_stream(cid, body.lesson_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
@router.get("/courses/{cid}/export")
async def export_course(cid: str) -> Response:
    """Export the course plan as a JSON file attachment."""
    record = get_course_store().get(cid)
    if record.plan is None:
        raise AppError("NO_PLAN", "No plan exists yet for this course.", 400)
    content = record.plan.model_dump_json(indent=2)
    filename = record.plan.title.replace(" ", "_").lower()[:40] + ".json"
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _syllabus_stream(
    cid: str,
    data: bytes,
    replace: bool,
) -> AsyncIterator[str]:
    """SSE generator for syllabus PDF restructuring."""
    from app.services.syllabus import merge_intake, restructure_syllabus

    record = get_course_store().get(cid)

    if record.plan is not None and not replace:
        yield _sse("error", {"code": "PLAN_EXISTS", "message": "A plan already exists. Send ?replace=true to overwrite."})
        return

    try:
        result = await restructure_syllabus(data)
    except AppError as exc:
        yield _sse("error", {"code": exc.code, "message": exc.message})
        return
    except Exception as exc:
        logger.exception("Syllabus restructuring failed")
        yield _sse("error", {"code": "SYLLABUS_ERROR", "message": str(exc)})
        return

    record.plan = result.course
    record.plan_version += 1
    record.intake = merge_intake(record.intake, result.inferred_intake)

    missing = missing_intake_fields(record.intake)
    yield _sse("intake_state", {"intake": record.intake.model_dump(), "missing": missing})
    yield _sse("plan_update", {
        "plan": record.plan.model_dump(),
        "plan_version": record.plan_version,
        "changed_ids": [m.id for m in record.plan.modules],
    })

    reply = f"I've restructured your syllabus into **{result.course.title}** — {result.course.description}"
    for word in reply.split(" "):
        yield _sse("token", {"text": word + " "})

    from app.models.llm import Message
    record.messages.append(Message(role="assistant", content=reply))
    yield _sse("done", {})


@router.post("/courses/{cid}/syllabus")
async def upload_syllabus(
    cid: str,
    file: UploadFile,
    replace: bool = Query(default=False),
) -> StreamingResponse:
    """Upload a syllabus PDF and restructure it into a course plan via SSE."""
    settings = get_settings()
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise AppError("UNSUPPORTED_FILE", "Only PDF files are accepted.", 415)
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise AppError("FILE_TOO_LARGE", f"File exceeds {settings.MAX_UPLOAD_MB} MB.", 413)
    return StreamingResponse(
        _syllabus_stream(cid, data, replace),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
