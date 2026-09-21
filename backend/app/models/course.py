"""Course planner Pydantic models."""
import uuid
from typing import Literal

from pydantic import BaseModel, Field


class Resource(BaseModel):
    """A learning resource linked to a lesson."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    title: str
    url: str
    type: Literal["video", "article", "exercise", "other"] = "other"
    validated: bool = False


class Lesson(BaseModel):
    """A single lesson within a module."""

    id: str  # e.g. "m1-l2"
    title: str
    duration_minutes: int = 30
    objectives: list[str] = []
    resources: list[Resource] = []


class Module(BaseModel):
    """A course module containing lessons."""

    id: str  # e.g. "m1"
    title: str
    lessons: list[Lesson] = []


class Course(BaseModel):
    """The full generated course plan."""

    title: str
    description: str = ""
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    total_weeks: int = 4
    modules: list[Module] = []


class IntakeData(BaseModel):
    """Fields collected during the intake conversation."""

    topic: str | None = None
    level: Literal["beginner", "intermediate", "advanced"] | None = None
    duration_weeks: int | None = None
    goals: list[str] = []
    prerequisites: list[str] = []
    extra: dict = Field(default_factory=dict)


# Fields required before plan generation
REQUIRED_INTAKE_FIELDS: list[str] = ["topic", "level", "duration_weeks"]


def missing_intake_fields(intake: IntakeData) -> list[str]:
    """Return list of required field names that are still None/empty."""
    missing: list[str] = []
    if not intake.topic:
        missing.append("topic")
    if intake.level is None:
        missing.append("level")
    if intake.duration_weeks is None:
        missing.append("duration_weeks")
    return missing
