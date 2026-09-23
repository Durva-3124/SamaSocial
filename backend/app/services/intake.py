"""Intake analysis: extract structured fields from a user message."""
from __future__ import annotations

import logging
import re
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
- duration_weeks (int): how many weeks they want the course to last (1–52)
- sessions_per_week (int): how many sessions per week they can commit to (1–7)
- age_group (str): the learner's age group (e.g. "adult", "teenager", "professional")
- prior_knowledge (str): what they already know relevant to the topic
- goals (list[str]): specific learning goals mentioned
- prerequisites (list[str]): prior knowledge they mentioned

Return ONLY the fields that are clearly stated. Omit fields that are not mentioned.
Return a JSON object with "intent" and only the intake fields you found."""


class _IntakeExtract(BaseModel):
    intent: Intent = "intake"
    topic: str | None = None
    level: str | None = None
    duration_weeks: int | None = None
    sessions_per_week: int | None = None
    age_group: str | None = None
    prior_knowledge: str | None = None
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
    explicit = _extract_explicit_fields(user_message, current_intake)
    candidate = current_intake.model_copy(deep=True)
    for field, value in explicit.items():
        if getattr(candidate, field, None) in (None, [], ""):
            setattr(candidate, field, value)
    if explicit and not missing_intake_fields(candidate):
        return candidate, "intake"

    try:
        extracted = await _llm.complete_json(
            context_msgs, system=_SYSTEM, schema=_IntakeExtract
        )
    except Exception as exc:
        logger.warning("Intake extraction failed: %s", exc)
        # Continue with deterministic parsing below. Providers sometimes
        # return an out-of-range value such as 12 sessions/week, causing
        # schema validation to fail even though the user's message is usable.
        extracted = _IntakeExtract(intent="intake")

    intent: Intent = extracted.intent
    updated = current_intake.model_copy(deep=True)

    # Preserve explicit answers when the provider returns a partial extraction.
    for field, value in explicit.items():
        if getattr(extracted, field, None) in (None, [], ""):
            setattr(extracted, field, value)

    if extracted.topic and not updated.topic:
        updated.topic = extracted.topic
    if extracted.level and extracted.level in _VALID_LEVELS and updated.level is None:
        updated.level = extracted.level  # type: ignore[assignment]
    if extracted.duration_weeks and updated.duration_weeks is None:
        updated.duration_weeks = extracted.duration_weeks
    if extracted.sessions_per_week and updated.sessions_per_week is None:
        updated.sessions_per_week = extracted.sessions_per_week
    if extracted.age_group and not updated.age_group:
        updated.age_group = extracted.age_group
    if extracted.prior_knowledge and not updated.prior_knowledge:
        updated.prior_knowledge = extracted.prior_knowledge
    if extracted.goals:
        existing = set(updated.goals)
        updated.goals = updated.goals + [g for g in extracted.goals if g not in existing]
    if extracted.prerequisites:
        existing = set(updated.prerequisites)
        updated.prerequisites = updated.prerequisites + [
            p for p in extracted.prerequisites if p not in existing
        ]

    return updated, intent


def _extract_explicit_fields(message: str, current_intake: IntakeData) -> dict:
    """Extract common labelled intake answers without another LLM call."""
    text = " ".join(message.replace("\n", " ").split())
    fields: dict = {}

    level = re.search(r"\b(beginner|intermediate|advanced)\b", text, re.I)
    if level:
        fields["level"] = level.group(1).lower()
    weeks = re.search(r"\b(\d{1,2})\s*(?:weeks?|wks?)\b", text, re.I)
    if weeks:
        fields["duration_weeks"] = int(weeks.group(1))
    sessions = re.search(r"\b(\d{1,2})\s*(?:sessions?|times?)\b", text, re.I)
    if sessions:
        count = int(sessions.group(1))
        # Users often give total sessions (e.g. 12 sessions in 4 weeks),
        # while the model stores sessions per week.
        if count <= 7:
            fields["sessions_per_week"] = count
        elif current_intake.duration_weeks and count % current_intake.duration_weeks == 0:
            per_week = count // current_intake.duration_weeks
            if 1 <= per_week <= 7:
                fields["sessions_per_week"] = per_week

    age = re.search(r"\bage\s*(?:is|:|-)?\s*(\d{1,3})\b", text, re.I)
    if age:
        fields["age_group"] = f"{age.group(1)}-year-old learner"

    for label, field in (("topic", "topic"), ("age", "age_group"), ("prior knowledge", "prior_knowledge")):
        match = re.search(rf"\b{re.escape(label)}\s*[:=-]\s*([^.;]+)", text, re.I)
        if match:
            fields[field] = match.group(1).strip()

    if "prior_knowledge" not in fields:
        yes_no = re.search(r"(?:^|[,;]|\band\s+)(yes|no)\s*[.!]?\s*$", text, re.I)
        if yes_no:
            fields["prior_knowledge"] = yes_no.group(1).lower()
    return fields


def intake_prompt(missing: list[str]) -> str:
    """Ask for all missing intake fields in one turn to avoid repetitive loops."""
    prompts = {
        "topic": "What subject or topic would you like to learn?",
        "level": "What is your current experience level — beginner, intermediate, or advanced?",
        "duration_weeks": "How many weeks would you like the course to last?",
        "sessions_per_week": "How many study sessions per week can you commit to?",
        "age_group": "Who is this course for — what age group or learner type?",
        "prior_knowledge": "What do you already know about this topic?",
    }
    questions = [prompts[field] for field in missing if field in prompts]
    if not questions:
        return "Could you tell me more about what you'd like to learn?"
    return "To build your full course plan, please answer these together:\n" + "\n".join(
        f"{index}. {question}" for index, question in enumerate(questions, 1)
    )
