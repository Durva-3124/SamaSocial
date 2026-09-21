"""Course planner API routes."""
import logging

from fastapi import APIRouter

from app.models.course import missing_intake_fields
from app.services.stores.course_store import get_course_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


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
