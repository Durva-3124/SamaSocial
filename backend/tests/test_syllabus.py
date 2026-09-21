"""Tests for syllabus PDF restructuring."""
import json
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.course import Course, IntakeData
from app.services.syllabus import SyllabusResult, merge_intake, restructure_syllabus
from tests.fakes import FakeLLM


def _make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), text)
    data = doc.tobytes()
    doc.close()
    return data


def _course_json() -> str:
    return json.dumps({
        "title": "Python Basics",
        "description": "Learn Python from scratch.",
        "level": "beginner",
        "total_weeks": 4,
        "modules": [
            {
                "id": "m1",
                "title": "Introduction",
                "lessons": [
                    {
                        "id": "m1-l1",
                        "title": "Variables",
                        "duration_minutes": 30,
                        "objectives": ["Declare variables"],
                        "resources": [],
                    }
                ],
            }
        ],
    })


# ── unit tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_restructure_syllabus_success():
    llm = FakeLLM(script=[_course_json()])
    pdf = _make_pdf("Week 1: Variables and data types. Week 2: Functions.")
    result = await restructure_syllabus(pdf, llm=llm)
    assert isinstance(result.course, Course)
    assert result.course.title == "Python Basics"
    assert result.inferred_intake["topic"] == "Python Basics"
    assert result.inferred_intake["level"] == "beginner"
    assert result.inferred_intake["duration_weeks"] == 4


@pytest.mark.asyncio
async def test_restructure_syllabus_no_text():
    doc = fitz.open()
    doc.new_page()  # blank page
    pdf = doc.tobytes()
    doc.close()
    with pytest.raises(Exception) as exc_info:
        await restructure_syllabus(pdf)
    assert "NO_TEXT_LAYER" in str(exc_info.value.code)


@pytest.mark.asyncio
async def test_restructure_syllabus_condenses_long_text():
    """Long syllabi trigger the condense path (>6000 words)."""
    long_text = ("word " * 7000).strip()
    pdf = _make_pdf(long_text[:3000])  # PDF can't hold 7000 words in one call

    # Patch extract_pdf_pages to return long text
    with patch(
        "app.services.syllabus.extract_pdf_pages",
        return_value=[(1, long_text)],
    ):
        # condense returns a summary, then restructure returns the course
        llm = FakeLLM(script=["condensed syllabus text", _course_json()])
        result = await restructure_syllabus(pdf, llm=llm)
    assert isinstance(result.course, Course)
    # ceil(7000/1500)=5 condense calls + 1 restructure call
    assert llm._idx == 6


def test_merge_intake_does_not_overwrite():
    intake = IntakeData(topic="Existing Topic", level="advanced")
    inferred = {"topic": "New Topic", "level": "beginner", "duration_weeks": 6}
    merged = merge_intake(intake, inferred)
    assert merged.topic == "Existing Topic"   # not overwritten
    assert merged.level == "advanced"          # not overwritten
    assert merged.duration_weeks == 6          # filled in


def test_merge_intake_fills_missing():
    intake = IntakeData()
    inferred = {"topic": "Python", "level": "beginner", "duration_weeks": 4}
    merged = merge_intake(intake, inferred)
    assert merged.topic == "Python"
    assert merged.duration_weeks == 4


# ── API route tests ───────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_syllabus_route_success(client):
    # Create a course
    r = await client.post("/api/courses")
    cid = r.json()["course_id"]

    pdf = _make_pdf("Week 1: Variables. Week 2: Functions.")

    with patch(
        "app.services.syllabus.restructure_syllabus",
        new_callable=AsyncMock,
        return_value=SyllabusResult(
            course=Course.model_validate_json(_course_json()),
            inferred_intake={"topic": "Python Basics", "level": "beginner", "duration_weeks": 4},
        ),
    ):
        r = await client.post(
            f"/api/courses/{cid}/syllabus",
            files={"file": ("syllabus.pdf", pdf, "application/pdf")},
        )

    assert r.status_code == 200
    events = [line for line in r.text.splitlines() if line.startswith("event:")]
    event_names = [e.replace("event: ", "") for e in events]
    assert "intake_state" in event_names
    assert "plan_update" in event_names
    assert "done" in event_names


@pytest.mark.asyncio
async def test_syllabus_route_plan_exists_blocked(client):
    r = await client.post("/api/courses")
    cid = r.json()["course_id"]

    pdf = _make_pdf("Week 1: Variables.")
    course = Course.model_validate_json(_course_json())

    with patch(
        "app.services.syllabus.restructure_syllabus",
        new_callable=AsyncMock,
        return_value=SyllabusResult(course=course, inferred_intake={}),
    ):
        # First upload — sets the plan
        await client.post(
            f"/api/courses/{cid}/syllabus",
            files={"file": ("s.pdf", pdf, "application/pdf")},
        )
        # Second upload without replace=true
        r2 = await client.post(
            f"/api/courses/{cid}/syllabus",
            files={"file": ("s.pdf", pdf, "application/pdf")},
        )

    assert "PLAN_EXISTS" in r2.text


@pytest.mark.asyncio
async def test_syllabus_route_replace(client):
    r = await client.post("/api/courses")
    cid = r.json()["course_id"]

    pdf = _make_pdf("Week 1: Variables.")
    course = Course.model_validate_json(_course_json())

    with patch(
        "app.services.syllabus.restructure_syllabus",
        new_callable=AsyncMock,
        return_value=SyllabusResult(course=course, inferred_intake={}),
    ):
        await client.post(
            f"/api/courses/{cid}/syllabus",
            files={"file": ("s.pdf", pdf, "application/pdf")},
        )
        r2 = await client.post(
            f"/api/courses/{cid}/syllabus?replace=true",
            files={"file": ("s.pdf", pdf, "application/pdf")},
        )

    assert "done" in r2.text
    assert "PLAN_EXISTS" not in r2.text


@pytest.mark.asyncio
async def test_syllabus_route_non_pdf_rejected(client):
    r = await client.post("/api/courses")
    cid = r.json()["course_id"]
    r2 = await client.post(
        f"/api/courses/{cid}/syllabus",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r2.status_code == 415
