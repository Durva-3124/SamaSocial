"""Tests for planner, course_chat, PATCH, export — no network."""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.course import Course, IntakeData, Module, Lesson
from app.models.llm import Message
from app.services.course_chat import course_chat_stream
from app.services.planner import generate_plan, refine_plan
from app.services.stores.course_store import CourseRecord, CourseStore
from tests.fakes import FakeLLM


# ── helpers ───────────────────────────────────────────────────────────────────

def _minimal_course_json() -> str:
    return json.dumps({
        "title": "Python Basics",
        "description": "Learn Python",
        "level": "beginner",
        "total_weeks": 2,
        "modules": [
            {
                "id": "m1", "title": "Intro",
                "lessons": [{"id": "m1-l1", "title": "Hello", "duration_minutes": 30,
                              "objectives": [], "resources": []}],
            }
        ],
    })


def _full_intake() -> IntakeData:
    return IntakeData(topic="Python", level="beginner", duration_weeks=2)


def _parse_sse(raw: str) -> list[dict]:
    events = []
    for block in raw.strip().split("\n\n"):
        lines = block.strip().splitlines()
        event = next((l[7:] for l in lines if l.startswith("event: ")), None)
        data_line = next((l[6:] for l in lines if l.startswith("data: ")), None)
        if event and data_line:
            events.append({"event": event, "data": json.loads(data_line)})
    return events


# ── planner ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_plan_returns_course():
    llm = FakeLLM(script=[_minimal_course_json()])
    course = await generate_plan(_full_intake(), llm=llm)
    assert course.title == "Python Basics"
    assert len(course.modules) == 1


@pytest.mark.asyncio
async def test_refine_plan_returns_updated_course():
    original = Course.model_validate_json(_minimal_course_json())
    updated_json = _minimal_course_json().replace("Python Basics", "Advanced Python")
    llm = FakeLLM(script=[updated_json])
    refined = await refine_plan(original, "Make it advanced", [], llm=llm)
    assert refined.title == "Advanced Python"


# ── course_chat_stream ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_course_chat_incomplete_intake_emits_intake_state_and_token():
    record = CourseRecord("test1")
    # LLM returns empty intake extract, then a token response
    intake_json = json.dumps({})
    llm = FakeLLM(script=[intake_json])

    events = []
    async for chunk in course_chat_stream(record, "I want to learn something", llm=llm):
        events.append(chunk)

    parsed = _parse_sse("".join(events))
    names = [e["event"] for e in parsed]
    assert "intake_state" in names
    assert "token" in names
    assert "done" in names


@pytest.mark.asyncio
async def test_course_chat_complete_intake_generates_plan():
    record = CourseRecord("test2")
    record.intake = _full_intake()

    intake_json = json.dumps({"topic": "Python", "level": "beginner", "duration_weeks": 2})
    plan_json = _minimal_course_json()
    llm = FakeLLM(script=[intake_json, plan_json])

    events = []
    async for chunk in course_chat_stream(record, "looks good", llm=llm):
        events.append(chunk)

    parsed = _parse_sse("".join(events))
    names = [e["event"] for e in parsed]
    assert "plan_update" in names
    plan_event = next(e["data"] for e in parsed if e["event"] == "plan_update")
    assert plan_event["plan"]["title"] == "Python Basics"
    assert plan_event["plan_version"] == 1


# ── PATCH route ───────────────────────────────────────────────────────────────

def test_patch_plan_updates_title():
    cs = CourseStore(ttl_minutes=10)
    record = cs.create()
    record.plan = Course.model_validate_json(_minimal_course_json())
    record.plan_version = 1

    with patch("app.api.courses.get_course_store", return_value=cs):
        client = TestClient(app)
        resp = client.patch(
            f"/api/courses/{record.id}/plan",
            json={"path": "/title", "value": "New Title"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"]["title"] == "New Title"
    assert data["plan_version"] == 2


def test_patch_plan_no_plan_returns_400():
    cs = CourseStore(ttl_minutes=10)
    record = cs.create()

    with patch("app.api.courses.get_course_store", return_value=cs):
        client = TestClient(app)
        resp = client.patch(
            f"/api/courses/{record.id}/plan",
            json={"path": "/title", "value": "x"},
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NO_PLAN"


def test_patch_plan_nested_field():
    cs = CourseStore(ttl_minutes=10)
    record = cs.create()
    record.plan = Course.model_validate_json(_minimal_course_json())

    with patch("app.api.courses.get_course_store", return_value=cs):
        client = TestClient(app)
        resp = client.patch(
            f"/api/courses/{record.id}/plan",
            json={"path": "/modules/0/title", "value": "Updated Module"},
        )
    assert resp.status_code == 200
    assert resp.json()["plan"]["modules"][0]["title"] == "Updated Module"


# ── export route ──────────────────────────────────────────────────────────────

def test_export_returns_json_attachment():
    cs = CourseStore(ttl_minutes=10)
    record = cs.create()
    record.plan = Course.model_validate_json(_minimal_course_json())

    with patch("app.api.courses.get_course_store", return_value=cs):
        client = TestClient(app)
        resp = client.get(f"/api/courses/{record.id}/export")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert "attachment" in resp.headers["content-disposition"]
    data = resp.json()
    assert data["title"] == "Python Basics"


def test_export_no_plan_returns_400():
    cs = CourseStore(ttl_minutes=10)
    record = cs.create()

    with patch("app.api.courses.get_course_store", return_value=cs):
        client = TestClient(app)
        resp = client.get(f"/api/courses/{record.id}/export")
    assert resp.status_code == 400
