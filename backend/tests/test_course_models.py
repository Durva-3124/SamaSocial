"""Tests for course models, store, intake, and routes — no network."""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.course import (
    Course, IntakeData, Module, Lesson,
    missing_intake_fields,
)
from app.models.llm import Message
from app.services.intake import analyse_turn, intake_prompt
from app.services.stores.course_store import CourseStore
from app.core.errors import AppError
from tests.fakes import FakeLLM


# ── model validation ──────────────────────────────────────────────────────────

def test_missing_intake_all_missing():
    intake = IntakeData()
    assert set(missing_intake_fields(intake)) == {
        "topic", "level", "duration_weeks", "sessions_per_week", "age_group", "prior_knowledge"
    }


def test_missing_intake_partial():
    intake = IntakeData(topic="Python", level="beginner")
    assert set(missing_intake_fields(intake)) == {"duration_weeks", "sessions_per_week", "age_group", "prior_knowledge"}


def test_missing_intake_none_missing():
    intake = IntakeData(
        topic="Python", level="beginner", duration_weeks=4,
        sessions_per_week=3, age_group="adult", prior_knowledge="none"
    )
    assert missing_intake_fields(intake) == []


def test_course_model_valid():
    course = Course(
        title="Python Basics",
        level="beginner",
        total_weeks=4,
        modules=[
            Module(
                id="m1",
                title="Intro",
                lessons=[Lesson(id="m1-l1", title="Hello World")],
            )
        ],
    )
    assert course.modules[0].lessons[0].id == "m1-l1"


# ── course store ──────────────────────────────────────────────────────────────

def test_course_store_create_and_get():
    store = CourseStore(ttl_minutes=10)
    record = store.create()
    fetched = store.get(record.id)
    assert fetched.id == record.id


def test_course_store_not_found():
    store = CourseStore(ttl_minutes=10)
    with pytest.raises(AppError) as exc_info:
        store.get("ghost")
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "COURSE_NOT_FOUND"


def test_course_store_ttl_eviction():
    from datetime import UTC, datetime, timedelta
    store = CourseStore(ttl_minutes=0)
    record = store.create()
    store._courses[record.id].last_active = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(AppError):
        store.get(record.id)


# ── intake service ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyse_turn_extracts_topic():
    payload = json.dumps({"topic": "machine learning", "level": "beginner"})
    llm = FakeLLM(script=[payload])
    intake, _intent = await analyse_turn("I want to learn ML", [], IntakeData(), llm=llm)
    assert intake.topic == "machine learning"
    assert intake.level == "beginner"


@pytest.mark.asyncio
async def test_analyse_turn_does_not_overwrite_existing():
    payload = json.dumps({"topic": "new topic"})
    llm = FakeLLM(script=[payload])
    existing = IntakeData(topic="Python")
    intake, _intent = await analyse_turn("something", [], existing, llm=llm)
    assert intake.topic == "Python"  # not overwritten


@pytest.mark.asyncio
async def test_analyse_turn_returns_current_on_llm_failure():
    class _BadLLM:
        async def complete_json(self, *a, **kw):
            raise ValueError("boom")

    existing = IntakeData(topic="Python")
    intake, _intent = await analyse_turn("hi", [], existing, llm=_BadLLM())
    assert intake.topic == "Python"


@pytest.mark.asyncio
async def test_analyse_turn_recovers_explicit_answers_when_llm_is_partial():
    payload = json.dumps({"intent": "intake", "topic": "Python"})
    llm = FakeLLM(script=[payload])
    intake, _intent = await analyse_turn(
        "topic: Python, level: beginner, duration: 4 weeks, 3 sessions per week, age: adult, prior knowledge: none",
        [],
        IntakeData(),
        llm=llm,
    )
    assert missing_intake_fields(intake) == []


@pytest.mark.asyncio
async def test_analyse_turn_understands_total_sessions_age_and_yes_no():
    llm = FakeLLM(script=[json.dumps({"intent": "intake"})])
    intake = IntakeData(duration_weeks=4)
    intake, _intent = await analyse_turn("12 sessions, age is 19 and yes", [], intake, llm=llm)
    assert intake.sessions_per_week == 3
    assert intake.age_group == "19-year-old learner"
    assert intake.prior_knowledge == "yes"


@pytest.mark.asyncio
async def test_analyse_turn_parses_answers_when_llm_json_is_invalid():
    class _BadLLM:
        async def complete_json(self, *args, **kwargs):
            raise ValueError("sessions_per_week must be 1-7")

    intake, _intent = await analyse_turn(
        "12 sessions, age is 19 and yes",
        [],
        IntakeData(duration_weeks=4),
        llm=_BadLLM(),
    )
    assert intake.sessions_per_week == 3
    assert intake.age_group == "19-year-old learner"
    assert intake.prior_knowledge == "yes"


@pytest.mark.asyncio
async def test_analyse_turn_skips_llm_when_explicit_answers_complete_intake():
    llm = FakeLLM(script=["not used"])
    intake, _intent = await analyse_turn(
        "topic: Python, beginner, 4 weeks, 3 sessions per week, age: 19, prior knowledge: none",
        [],
        IntakeData(),
        llm=llm,
    )
    assert missing_intake_fields(intake) == []
    assert llm.calls == []


def test_intake_prompt_returns_string():
    assert "topic" in intake_prompt(["topic"]).lower() or len(intake_prompt(["topic"])) > 0
    assert len(intake_prompt([])) > 0


# ── course API routes ─────────────────────────────────────────────────────────

def test_create_course():
    client = TestClient(app)
    resp = client.post("/api/courses")
    assert resp.status_code == 201
    assert "course_id" in resp.json()


def test_get_course_initial_state():
    client = TestClient(app)
    cid = client.post("/api/courses").json()["course_id"]
    resp = client.get(f"/api/courses/{cid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] is None
    assert data["plan_version"] == 0
    assert set(data["missing"]) == {"topic", "level", "duration_weeks", "sessions_per_week", "age_group", "prior_knowledge"}
    assert data["messages"] == []


def test_get_course_not_found():
    client = TestClient(app)
    resp = client.get("/api/courses/doesnotexist")
    assert resp.status_code == 404
