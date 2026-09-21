"""Syllabus PDF restructuring service."""
import asyncio
import logging

from app.core.errors import AppError
from app.models.course import Course, IntakeData, missing_intake_fields
from app.models.llm import Message
from app.services.ingestion.pdf import extract_pdf_pages
from app.services.llm import LLMClient, get_llm

logger = logging.getLogger(__name__)

_MAX_WORDS_DIRECT = 6000

_CONDENSE_SYSTEM = (
    "You are summarising sections of a course syllabus. "
    "Preserve every topic name, week/hour estimate, and learning objective. "
    "Output only the condensed text, no commentary."
)

_RESTRUCTURE_SYSTEM = """You are an expert curriculum designer.
Restructure the provided syllabus into a complete course plan as JSON.
The JSON must match this structure exactly:
{
  "title": "string",
  "description": "string",
  "level": "beginner|intermediate|advanced",
  "total_weeks": int,
  "modules": [
    {
      "id": "m1",
      "title": "string",
      "lessons": [
        {
          "id": "m1-l1",
          "title": "string",
          "duration_minutes": int,
          "objectives": ["string"],
          "resources": []
        }
      ]
    }
  ]
}
Rules:
- Keep the original topics and intent.
- Fix ordering problems; ensure difficulty increases across modules.
- Fill missing objectives (make them measurable: "Write a function that...").
- Add prerequisites per module based on prior modules.
- Module ids: m1, m2, ... Lesson ids: m1-l1, m1-l2, ...
- One module per week (or per major topic block if weeks are not stated).
- Each module should have 3-5 lessons."""


class SyllabusResult:
    """Result of restructuring a syllabus PDF."""

    def __init__(self, course: Course, inferred_intake: dict) -> None:
        self.course = course
        self.inferred_intake = inferred_intake


async def _condense_text(text: str, llm: LLMClient) -> str:
    """Condense long syllabus text by summarising 1500-word sections in parallel."""
    words = text.split()
    section_size = 1500
    sections = [
        " ".join(words[i : i + section_size])
        for i in range(0, len(words), section_size)
    ]
    sem = asyncio.Semaphore(3)

    async def _summarise(section: str) -> str:
        async with sem:
            return await llm.complete(
                [Message(role="user", content=section)],
                system=_CONDENSE_SYSTEM,
            )

    summaries = await asyncio.gather(*[_summarise(s) for s in sections])
    return "\n\n".join(summaries)


async def restructure_syllabus(
    data: bytes,
    *,
    llm: LLMClient | None = None,
) -> SyllabusResult:
    """Extract text from a PDF syllabus and restructure it into a Course.

    Raises AppError on invalid PDF or no extractable text.
    """
    _llm = llm or get_llm()

    pages = await asyncio.to_thread(extract_pdf_pages, data)
    if not pages:
        raise AppError(
            "NO_TEXT_LAYER",
            "This PDF looks scanned or image-only, so no text could be extracted.",
            422,
        )

    full_text = "\n\n".join(text for _, text in pages)
    word_count = len(full_text.split())

    if word_count > _MAX_WORDS_DIRECT:
        logger.info("Syllabus is %d words — condensing before restructure.", word_count)
        full_text = await _condense_text(full_text, _llm)

    messages = [Message(role="user", content=f"Syllabus:\n\n{full_text}")]
    course = await _llm.complete_json(messages, system=_RESTRUCTURE_SYSTEM, schema=Course)

    # Infer intake fields from the generated plan
    inferred: dict = {
        "topic": course.title,
        "level": course.level,
        "duration_weeks": course.total_weeks,
    }

    return SyllabusResult(course=course, inferred_intake=inferred)


def merge_intake(intake: IntakeData, inferred: dict) -> IntakeData:
    """Merge inferred intake fields without overwriting existing values."""
    data = intake.model_dump()
    for key, value in inferred.items():
        if data.get(key) is None and value is not None:
            data[key] = value
    return IntakeData.model_validate(data)
