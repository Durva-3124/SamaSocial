"""Tests for chat pipeline and SSE route — no network, no real LLM."""
import json
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.chunk import Chunk, Locator
from app.models.session import Session, SourceRecord
from app.services.chat import chat_stream
from app.services.stores.session_store import SessionStore
from app.services.stores.vector_store import VectorStore
from tests.fakes import FakeEmbedder, FakeLLM


# ── helpers ───────────────────────────────────────────────────────────────────

def _unit_vec(dim: int, idx: int) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[idx] = 1.0
    return v


@pytest.fixture()
async def session_with_chunk() -> tuple[Session, VectorStore]:
    session = Session(id="sess1")
    session.sources["src1"] = SourceRecord(
        id="src1", type="pdf", name="notes.pdf", status="ready"
    )
    chunk = Chunk(source_id="src1", source_type="pdf", text="python loops", locator=Locator(page=1))
    vs = VectorStore()
    emb = FakeEmbedder()
    vec = await emb.embed([chunk.text])
    vs.add("sess1", [chunk], vec)
    return session, vs


def _parse_sse(raw: str) -> list[dict]:
    """Parse raw SSE text into list of {event, data} dicts."""
    events = []
    for block in raw.strip().split("\n\n"):
        lines = block.strip().splitlines()
        event = next((l[7:] for l in lines if l.startswith("event: ")), None)
        data_line = next((l[6:] for l in lines if l.startswith("data: ")), None)
        if event and data_line:
            events.append({"event": event, "data": json.loads(data_line)})
    return events


# ── chat_stream unit tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_stream_emits_tokens_and_done(session_with_chunk):
    session, vs = session_with_chunk
    llm = FakeLLM(script=["Here is the answer [S1]."])
    emb = FakeEmbedder()

    events = []
    async for chunk in chat_stream(session, "python loops", "normal", llm=llm, embedder=emb, vector_store=vs):
        events.append(chunk)

    raw = "".join(events)
    parsed = _parse_sse(raw)
    event_names = [e["event"] for e in parsed]

    assert "token" in event_names
    assert "done" in event_names
    done = next(e["data"] for e in parsed if e["event"] == "done")
    assert "declined" in done
    assert "used_source_ids" in done


@pytest.mark.asyncio
async def test_chat_stream_declined_when_no_chunks():
    session = Session(id="empty")
    vs = VectorStore()  # no chunks
    llm = FakeLLM(script=["I don't know."])
    emb = FakeEmbedder()

    events = []
    async for chunk in chat_stream(session, "anything", "normal", llm=llm, embedder=emb, vector_store=vs):
        events.append(chunk)

    parsed = _parse_sse("".join(events))
    done = next(e["data"] for e in parsed if e["event"] == "done")
    assert done["declined"] is True


@pytest.mark.asyncio
async def test_chat_stream_citations_emitted_when_label_in_response(session_with_chunk):
    session, vs = session_with_chunk
    llm = FakeLLM(script=["Use [S1] for loops."])
    emb = FakeEmbedder()

    events = []
    async for chunk in chat_stream(session, "python loops", "normal", llm=llm, embedder=emb, vector_store=vs):
        events.append(chunk)

    parsed = _parse_sse("".join(events))
    citations_events = [e for e in parsed if e["event"] == "citations"]
    assert len(citations_events) == 1
    items = citations_events[0]["data"]["items"]
    assert items[0]["label"] == "S1"
    assert items[0]["source_name"] == "notes.pdf"


@pytest.mark.asyncio
async def test_chat_stream_history_updated(session_with_chunk):
    session, vs = session_with_chunk
    llm = FakeLLM(script=["Answer [S1]."])
    emb = FakeEmbedder()

    async for _ in chat_stream(session, "question", "normal", llm=llm, embedder=emb, vector_store=vs):
        pass

    assert len(session.history) == 2
    assert session.history[0].role == "user"
    assert session.history[0].content == "question"
    assert session.history[1].role == "assistant"


# ── SSE route integration ─────────────────────────────────────────────────────

def test_chat_route_streams_sse():
    ss = SessionStore(ttl_minutes=10)
    session = ss.create()
    session.sources["src1"] = SourceRecord(
        id="src1", type="pdf", name="doc.pdf", status="ready"
    )
    vs = VectorStore()
    emb = FakeEmbedder()
    llm = FakeLLM(script=["Hello [S1]."])

    with (
        patch("app.api.chat.get_session_store", return_value=ss),
        patch("app.services.chat.get_llm", return_value=llm),
        patch("app.services.chat.get_embedder", return_value=emb),
        patch("app.services.chat.get_vector_store", return_value=vs),
    ):
        client = TestClient(app)
        resp = client.post(
            f"/api/sessions/{session.id}/chat",
            json={"message": "hello", "mode": "normal"},
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    parsed = _parse_sse(resp.text)
    assert any(e["event"] == "done" for e in parsed)


def test_chat_route_unknown_session():
    client = TestClient(app)
    resp = client.post("/api/sessions/ghost/chat", json={"message": "hi"})
    assert resp.status_code == 404
