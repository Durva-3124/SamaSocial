"""Course planner Pydantic models."""
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DifficultyLevel = Literal["beginner", "intermediate", "advanced"]


class Audience(BaseModel):
    """Target audience descriptor."""

    age_group: str
    level: DifficultyLevel
    prior_knowledge: str


class Duration(BaseModel):
    """Course duration descriptor."""

    weeks: int = Field(..., ge=1, le=52)
    sessions_per_week: int = Field(..., ge=1, le=7)
    session_minutes: int = Field(..., ge=15, le=240)


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
    difficulty: DifficultyLevel = "beginner"
    objectives: list[str] = []
    topics: list[str] = []
    resources: list[Resource] = []


class Module(BaseModel):
    """A course module containing lessons."""

    id: str  # e.g. "m1"
    title: str
    difficulty: DifficultyLevel = "beginner"
    prerequisites: list[str] = []
    lessons: list[Lesson] = []


class Course(BaseModel):
    """The full generated course plan."""

    title: str
    description: str = ""
    level: DifficultyLevel = "beginner"
    total_weeks: int = 4
    goals: list[str] = []
    audience: Audience | None = None
    duration: Duration | None = None
    modules: list[Module] = []

    @model_validator(mode="after")
    def _check_bounds(self) -> "Course":
        from app.core.errors import AppError

        if len(self.modules) > 8:
            raise AppError(
                "PLAN_TOO_LARGE",
                f"Course may have at most 8 modules, got {len(self.modules)}",
                422,
            )
        total_lessons = sum(len(m.lessons) for m in self.modules)
        if total_lessons > 60:
            raise AppError(
                "PLAN_TOO_LARGE",
                f"Course may have at most 60 lessons total, got {total_lessons}",
                422,
            )
        return self


class IntakeData(BaseModel):
    """Fields collected during the intake conversation."""

    topic: str | None = None
    level: DifficultyLevel | None = None
    duration_weeks: int | None = None
    sessions_per_week: int | None = None
    age_group: str | None = None
    prior_knowledge: str | None = None
    goals: list[str] = []
    prerequisites: list[str] = []
    extra: dict = Field(default_factory=dict)

    @field_validator("duration_weeks")
    @classmethod
    def _check_weeks(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 52):
            from app.core.errors import AppError
            raise AppError("INVALID_VALUE", f"duration_weeks must be 1–52, got {v}", 422)
        return v

    @field_validator("sessions_per_week")
    @classmethod
    def _check_sessions(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 7):
            from app.core.errors import AppError
            raise AppError("INVALID_VALUE", f"sessions_per_week must be 1–7, got {v}", 422)
        return v


# Fields required before plan generation
REQUIRED_INTAKE_FIELDS: list[str] = [
    "topic", "level", "duration_weeks", "sessions_per_week", "age_group", "prior_knowledge"
]


def missing_intake_fields(intake: IntakeData) -> list[str]:
    """Return list of required field names that are still None/empty."""
    missing: list[str] = []
    if not intake.topic:
        missing.append("topic")
    if intake.level is None:
        missing.append("level")
    if intake.duration_weeks is None:
        missing.append("duration_weeks")
    if intake.sessions_per_week is None:
        missing.append("sessions_per_week")
    if not intake.age_group:
        missing.append("age_group")
    if not intake.prior_knowledge:
        missing.append("prior_knowledge")
    return missing
