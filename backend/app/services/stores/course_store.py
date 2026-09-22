"""In-memory course store with TTL eviction."""
import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from threading import Lock

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.course import Course, IntakeData
from app.models.llm import Message

logger = logging.getLogger(__name__)


class CourseRecord:
    """Mutable container for a single course planning session."""

    def __init__(self, course_id: str) -> None:
        self.id = course_id
        self.intake = IntakeData()
        self.plan: Course | None = None
        self.plan_version: int = 0
        self.messages: list[Message] = []
        self.last_active: datetime = datetime.now(UTC)
        self.lock: asyncio.Lock = asyncio.Lock()  # guards plan + plan_version mutations

    def touch(self) -> None:
        """Update last_active timestamp."""
        self.last_active = datetime.now(UTC)


class CourseStore:
    """Thread-safe in-memory store for CourseRecord objects with TTL eviction."""

    def __init__(self, ttl_minutes: int) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._courses: dict[str, CourseRecord] = {}
        self._lock = Lock()

    def create(self) -> CourseRecord:
        """Create and store a new course record."""
        record = CourseRecord(course_id=uuid.uuid4().hex)
        with self._lock:
            self._evict()
            self._courses[record.id] = record
        return record

    def get(self, course_id: str) -> CourseRecord:
        """Return the course record or raise AppError(404)."""
        with self._lock:
            self._evict()
            record = self._courses.get(course_id)
        if record is None:
            raise AppError("COURSE_NOT_FOUND", f"Course {course_id!r} not found.", 404)
        record.touch()
        return record

    def _evict(self) -> None:
        """Remove expired records (call under lock)."""
        cutoff = datetime.now(UTC) - self._ttl
        expired = [cid for cid, r in self._courses.items() if r.last_active < cutoff]
        for cid in expired:
            logger.debug("Evicting expired course %s", cid)
            del self._courses[cid]


@lru_cache
def get_course_store() -> CourseStore:
    """Return the singleton CourseStore."""
    return CourseStore(ttl_minutes=get_settings().SESSION_TTL_MINUTES)
