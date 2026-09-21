"""Course planner API routes."""
import json
import logging

from fastapi import APIRouter, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.errors import AppError
from app.models.course import Course, missing_intake_fields
from app.services.course_chat import course_chat_stream
from app.services.stores.course_store import get_course_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ── helpers ───────────────────────────────────────────────────────────────────

def _apply_json_pointer(plan: Course, pointer: str, value: object) -> Course:
    """Apply an RFC 6901 JSON Pointer patch to the plan and return updated Course.

    Supports simple paths like /title, /modules/0/title, /modules/0/lessons/1/title.
    """
    data = json.loads(plan.model_dump_json())
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer.lstrip("/").split("/")]
    node = data
    for part in parts[:-1]:
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (IndexError, ValueError) as exc:
                raise AppError("INVALID_POINTER", f"Invalid JSON pointer: {pointer}", 400) from exc
        elif isinstance(node, dict):
            if part not in node:
                raise AppError("INVALID_POINTER", f"Key {part!r} not found.", 400)
            node = node[part]
        else:
            raise AppError("INVALID_POINTER", f"Cannot traverse into {type(node).__name__}.", 400)

    last = parts[-1]
    if isinstance(node, list):
        try:
            node[int(last)] = value
        except (IndexError, ValueError) as exc:
            raise AppError("INVALID_POINTER", f"Invalid index {last!r}.", 400) from exc
    elif isinstance(node, dict):
        node[last] = value
    else:
        raise AppError("INVALID_POINTER", "Cannot set value on a scalar.", 400)

    return Course.model_validate(data)


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
    record.plan = _apply_json_pointer(record.plan, body.path, body.value)
    record.plan_version += 1
    return {"plan": record.plan.model_dump(), "plan_version": record.plan_version}


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
