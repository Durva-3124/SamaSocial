"""Course plan generation and refinement via LLM."""
import logging

from app.models.course import Course, IntakeData, Lesson, Module
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
Create one module per week. Each module should have 3-5 lessons.
Module ids: m1, m2, ... Lesson ids: m1-l1, m1-l2, ..."""

_REFINE_SYSTEM = """You are an expert curriculum designer.
The student has feedback on their course plan. Apply their requested changes and return
the complete updated course plan as JSON with the same structure as before.
Keep all unchanged parts exactly as they are."""


async def generate_plan(
    intake: IntakeData,
    *,
    llm: LLMClient | None = None,
) -> Course:
    """Generate a full Course from completed intake data."""
    _llm = llm or get_llm()
    intake_summary = (
        f"Topic: {intake.topic}\n"
        f"Level: {intake.level}\n"
        f"Duration: {intake.duration_weeks} weeks\n"
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
    import json
    plan_json = current_plan.model_dump_json(indent=2)
    context = history[-4:]
    messages = context + [
        Message(
            role="user",
            content=f"Current plan:\n{plan_json}\n\nFeedback: {feedback}",
        )
    ]
    return await _llm.complete_json(messages, system=_REFINE_SYSTEM, schema=Course)
