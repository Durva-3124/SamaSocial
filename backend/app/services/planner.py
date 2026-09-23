"""Course plan generation and refinement via LLM."""
import json
import logging

from app.models.course import Course, IntakeData
from app.models.llm import Message
from app.services.llm import LLMClient, get_llm

logger = logging.getLogger(__name__)

_GENERATE_SYSTEM = """You are an expert curriculum designer.
Given the student's intake information, generate a complete course plan as JSON.
The JSON must match this structure exactly:
{
  "title": "string",
  "description": "string",
  "level": "beginner|intermediate|advanced",
  "total_weeks": int,
  "goals": ["string"],
  "audience": {
    "age_group": "string",
    "level": "beginner|intermediate|advanced",
    "prior_knowledge": "string"
  },
  "duration": {
    "weeks": int,
    "sessions_per_week": int,
    "session_minutes": int
  },
  "modules": [
    {
      "id": "m1",
      "title": "string",
      "difficulty": "beginner|intermediate|advanced",
      "prerequisites": ["concrete topic string"],
      "lessons": [
        {
          "id": "m1-l1",
          "title": "string",
          "duration_minutes": int,
          "difficulty": "beginner|intermediate|advanced",
          "objectives": ["string"],
          "topics": ["string"],
          "resources": []
        }
      ]
    }
  ]
}

Rules:
- Module count: exactly one module per week, maximum 8 modules.
- Lessons per module: approximately sessions_per_week (within 1). E.g. if sessions_per_week=3, each module should have 2–4 lessons.
- Total lessons across all modules must not exceed 60.
- difficulty MUST be non-decreasing across the entire course — both at module level and lesson level. Start at the course level and progress toward "advanced" only if the course warrants it.
- prerequisites on each module must be concrete topic names (e.g. "variables and loops"), not vague phrases like "previous module".
- Module ids: m1, m2, ... Lesson ids: m1-l1, m1-l2, ...
- duration.session_minutes: typical lesson length in minutes (15–240).
- audience.level must match the top-level level field."""

_REFINE_SYSTEM = """You are an expert curriculum designer.
The student has feedback on their course plan. Apply their requested changes and return
the complete updated course plan as JSON with the same structure as before.
Keep all unchanged parts exactly as they are.

Rules to maintain during refinement:
- difficulty must remain non-decreasing across all modules and lessons.
- prerequisites must remain concrete topic names.
- Module count must not exceed 8; total lessons must not exceed 60.
- lessons per module should remain approximately sessions_per_week (within 1)."""


async def generate_plan(
    intake: IntakeData,
    *,
    llm: LLMClient | None = None,
) -> Course:
    """Generate a full Course from completed intake data."""
    _llm = llm or get_llm()
    spw = min(intake.sessions_per_week or 3, 4)
    weeks = min(intake.duration_weeks or 4, 8)
    intake_summary = (
        f"Topic: {intake.topic}\n"
        f"Level: {intake.level}\n"
        f"Duration: {weeks} weeks (generate no more than {weeks} modules)\n"
        f"Sessions per week: {spw}\n"
        f"Age group: {intake.age_group or 'not specified'}\n"
        f"Prior knowledge: {intake.prior_knowledge or 'none'}\n"
        f"Goals: {', '.join(intake.goals) or 'not specified'}\n"
        f"Prerequisites: {', '.join(intake.prerequisites) or 'none'}"
    )
    messages = [Message(role="user", content=f"Student intake:\n{intake_summary}")]
    return await _llm.complete_json(messages, system=_GENERATE_SYSTEM, schema=Course)


async def refine_plan(
    current_plan: Course,
    feedback: str,
    history: list[Message],
    *,
    llm: LLMClient | None = None,
) -> Course:
    """Apply user feedback to an existing plan and return the updated Course."""
    _llm = llm or get_llm()
    plan_json = current_plan.model_dump_json(indent=2)
    context = history[-4:]
    messages = context + [
        Message(
            role="user",
            content=f"Current plan:\n{plan_json}\n\nFeedback: {feedback}",
        )
    ]
    return await _llm.complete_json(messages, system=_REFINE_SYSTEM, schema=Course)
