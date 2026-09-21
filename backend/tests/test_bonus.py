"""Tests for summarise, quiz service, and quiz route — no network."""
import json
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.chunk import Chunk, Locator
from app.models.session import Session, SourceRecord
from app.services.quiz import generate_quiz
from app.services.summarise import summarise_source
from app.services.stores.session_store import SessionStore
from app.services.stores.vector_store import VectorStore
from tests.fakes import FakeEmbedder, FakeLLM


def _chunk(text: str, source_id: str = "s1") -> Chunk:
    return Chunk(source_id=source_id, source_type="pdf", text=text, locator=Locator(page=1))


# ── summarise_source ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summarise_returns_summary_and_topics():
    payload = json.dumps({"summary": "A short summary.", "topics": ["loops", "functions"]})
    llm = FakeLLM(script=[payload])
    summary, topics = await summarise_source([_chunk("python loops")], llm=llm)
    assert summary == "A short summary."
    assert "loops" in topics


@pytest.mark.asyncio
async def test_summarise_returns_empty_on_llm_failure():
    from pydantic import ValidationError

    class _BadLLM:
        async def complete_json(self, *a, **kw):
            raise ValueError("boom")

    summary, topics = await summarise_source([_chunk("text")], llm=_BadLLM())
    assert summary == ""
    assert topics == []


# ── generate_quiz ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_quiz_returns_questions():
    q = {
        "question": "What is a loop?",
        "options": ["A", "B", "C", "D"],
        "answer_index": 0,
        "explanation": "A loop repeats.",
        "source_id": "s1",
        "locator_text": "page 1",
    }
    payload = json.dumps({"questions": [q]})
    llm = FakeLLM(script=[payload])
    questions = await generate_quiz([_chunk("python loops")], num_questions=1, llm=llm)
    assert len(questions) == 1
    assert questions[0]["question"] == "What is a loop?"
    assert len(questions[0]["options"]) == 4


# ── quiz route ────────────────────────────────────────────────────────────────

def _setup_session_with_chunks() -> tuple[SessionStore, VectorStore, Session]:
    ss = SessionStore(ttl_minutes=10)
    vs = VectorStore()
    session = ss.create()
    session.sources["src1"] = SourceRecord(id="src1", type="pdf", name="doc.pdf", status="ready")

    chunk = _chunk("python loops", "src1")
    import asyncio
    emb = FakeEmbedder()
    vec = asyncio.run(emb.embed([chunk.text]))
    vs.add(session.id, [chunk], vec)
    return ss, vs, session


def test_quiz_route_returns_questions():
    ss, vs, session = _setup_session_with_chunks()
    q = {
        "question": "What is a loop?",
        "options": ["A", "B", "C", "D"],
        "answer_index": 0,
        "explanation": "Repeats.",
        "source_id": "src1",
        "locator_text": "page 1",
    }
    llm = FakeLLM(script=[json.dumps({"questions": [q]})])

    with (
        patch("app.api.bonus.get_session_store", return_value=ss),
        patch("app.api.bonus.get_vector_store", return_value=vs),
        patch("app.api.bonus.get_llm", return_value=llm),
    ):
        client = TestClient(app)
        resp = client.post(
            f"/api/sessions/{session.id}/quiz",
            json={"num_questions": 1},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "questions" in data
    assert len(data["questions"]) == 1


def test_quiz_route_no_sources_returns_422():
    ss = SessionStore(ttl_minutes=10)
    vs = VectorStore()
    session = ss.create()

    with (
        patch("app.api.bonus.get_session_store", return_value=ss),
        patch("app.api.bonus.get_vector_store", return_value=vs),
    ):
        client = TestClient(app)
        resp = client.post(
            f"/api/sessions/{session.id}/quiz",
            json={"num_questions": 3},
        )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NO_SOURCES"
