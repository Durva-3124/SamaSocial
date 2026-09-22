"""Intake analysis: extract structured fields from a user message."""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from app.models.course import IntakeData, missing_intake_fields
from app.models.llm import Message
from app.services.llm import LLMClient, get_llm

logger = logging.getLogger(__name__)

Intent = Literal["intake", "refine", "clarify"]

_SYSTEM = """You are a course planning assistant collecting information from a student.

First, classify the user's intent as one of:
- "intake": they are providing course details (topic, level, duration, goals, etc.)
- "refine": they are giving SPECIFIC feedback on an existing plan (e.g. "make module 2 simpler",
  "add more exercises", "shorten to 4 weeks", "focus on practical projects")
- "clarify": their message is too vague to act on (e.g. "make it better", "improve it",
  "change it", "fix it") — no specific module, lesson, or change is mentioned

Then extract any of these fields that are clearly stated:
- topic (str): the subject they want to learn
- level (str): one of "beginner", "intermediate", "advanced"
- duration_weeks (int): how many weeks they want the course to last
- goals (list[str]): specific learning goals mentioned
- prerequisites (list[str]): prior knowledge they mentioned

Return ONLY the fields that are clearly stated. Omit fields that are not mentioned.
Return a JSON object with "intent" and only the intake fields you found."""


class _IntakeExtract(BaseModel):
    intent: Intent = "intake"
    topic: str | None = None
    level: str | None = None
    duration_weeks: int | None = None
    goals: list[str] = []
    prerequisites: list[str] = []


_VALID_LEVELS = {"beginner", "intermediate", "advanced"}


async def analyse_turn(
    user_message: str,
    history: list[Message],
    current_intake: IntakeData,
    *,
    llm: LLMClient | None = None,
) -> tuple[IntakeData, Intent]:
    """Merge any newly extracted intake fields into current_intake.

    Returns (updated_intake, intent).
    Never overwrites an already-set field unless the new value is non-null.
    """
    _llm = llm or get_llm()
    context_msgs = history[-6:] + [Message(role="user", content=user_message)]

    try:
        extracted = await _llm.complete_json(
            context_msgs, system=_SYSTEM, schema=_IntakeExtract
        )
    except Exception as exc:
        logger.warning("Intake extraction failed: %s", exc)
        return current_intake, "intake"

    intent: Intent = extracted.intent
    updated = current_intake.model_copy(deep=True)

    if extracted.topic and not updated.topic:
        updated.topic = extracted.topic
    if extracted.level and extracted.level in _VALID_LEVELS and updated.level is None:
        updated.level = extracted.level  # type: ignore[assignment]
    if extracted.duration_weeks and updated.duration_weeks is None:
        updated.duration_weeks = extracted.duration_weeks
    if extracted.goals:
        existing = set(updated.goals)
        updated.goals = updated.goals + [g for g in extracted.goals if g not in existing]
    if extracted.prerequisites:
        existing = set(updated.prerequisites)
        updated.prerequisites = updated.prerequisites + [
            p for p in extracted.prerequisites if p not in existing
        ]

    return updated, intent


def intake_prompt(missing: list[str]) -> str:
    """Return a natural-language question asking for the next missing field."""
    prompts = {
        "topic": "What subject or topic would you like to learn?",
        "level": "What is your current experience level — beginner, intermediate, or advanced?",
        "duration_weeks": "How many weeks would you like the course to last?",
    }
    for field in missing:
        if field in prompts:
            return prompts[field]
    return "Could you tell me more about what you'd like to learn?"
