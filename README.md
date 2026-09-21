# Samasocial AI

## Overview

Samasocial AI is a two-feature learning platform powered by an OpenAI-compatible LLM.

- **Task 1 — Learning Assistant**: Upload PDFs, PowerPoints, YouTube videos, or web pages and chat with them. The assistant retrieves the most relevant chunks, answers with inline citations, and can generate a multiple-choice quiz from your sources.
- **Task 2 — Course Planner**: Have a conversation to describe your learning goal. The AI collects your topic, level, and timeline, then generates a structured week-by-week course plan with modules, lessons, and enriched resources. You can refine the plan through follow-up messages or by clicking any field to edit it inline.

## Features

### Task 1: Learning Assistant

- Upload `.pdf` / `.pptx` files or paste YouTube / web URLs
- Background ingestion with 2-second status polling
- RAG pipeline: embed query → cosine similarity retrieval → LLM answer with `[S1]` inline citations
- Normal and Simple (beginner-friendly) answer modes
- Auto-generated source summary and topic tags after ingestion
- Multiple-choice quiz generation from any subset of sources

### Task 2: Course Planner

- Conversational intake — collects topic, level, duration, goals, prerequisites
- Generates a full course plan (modules → lessons → objectives) once intake is complete
- Refines the plan in response to follow-up feedback
- Inline editing of any title, description, or summary — PATCH sent on blur
- Resource enrichment per lesson: YouTube API → Tavily → LLM stubs → HEAD validation
- Export course plan as JSON
- Live SSE streaming for all chat and resource-refresh operations

## Architecture

```
frontend/          React + Vite + TypeScript
  src/api/         Typed fetch wrappers (sessions.ts, courses.ts)
  src/hooks/       useSession, useChat, useCourse — all state lives here
  src/components/  SourcePanel, ChatPanel, QuizModal, CourseChatPanel, PlanViewer
  src/pages/       LearningAssistant, CoursePlanner

backend/           Python 3.11 + FastAPI + Pydantic v2
  app/api/         Thin route handlers (sessions, chat, bonus, courses)
  app/services/    Business logic
    llm.py         Single LLM client (stream_chat, complete_json)
    embeddings.py  sentence-transformers embedder (asyncio.to_thread)
    retrieval.py   Retriever — embed query, cosine search, min-score filter
    ingest_manager.py  Background ingest (PDF/PPTX/YouTube/web) + summarise
    chat.py        RAG pipeline → SSE
    summarise.py   Post-ingest summary + topic extraction
    quiz.py        MCQ generation from source chunks
    intake.py      Conversational intake field extraction + merge
    planner.py     generate_plan / refine_plan via LLM JSON mode
    course_chat.py SSE pipeline: intake → plan_update → token stream
    resources.py   YouTube API → Tavily → LLM stubs → URL validation
    stores/        SessionStore (TTL), VectorStore (NumPy cosine), CourseStore
  app/models/      Pydantic schemas (Session, Chunk, Course, IntakeData, …)
  app/core/        config.py (Settings), errors.py (AppError), url_safety.py
  tests/           137 offline tests — FakeLLM, FakeEmbedder, AsyncMock
```

All LLM calls go through `app/services/llm.py`. All embeddings go through `app/services/embeddings.py`. Config is centralised in `app/core/config.py` — `os.environ` is never read elsewhere.

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- An OpenAI-compatible API key (e.g. [Groq](https://console.groq.com))

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate  |  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### Running Tests

```bash
cd backend && pytest -q
cd frontend && npx vitest run
```

### Running the Evaluation

```bash
cd backend
python -m eval.make_fixtures
python -m eval.run_eval
```

## Environment Variables

| Name | Required | Default | Purpose |
|---|---|---|---|
| LLM_BASE_URL | No | https://api.groq.com/openai/v1 | OpenAI-compatible provider base URL |
| LLM_API_KEY | Yes | — | Provider API key |
| LLM_MODEL | Yes | — | Model name (e.g. llama-3.3-70b-versatile) |
| EMBEDDING_MODEL | No | sentence-transformers/all-MiniLM-L6-v2 | Local embedding model |
| FRONTEND_ORIGIN | No | http://localhost:5173 | CORS allowed origin |
| MAX_UPLOAD_MB | No | 25 | Max file upload size |
| SESSION_TTL_MINUTES | No | 120 | In-memory session TTL |
| RETRIEVAL_TOP_K | No | 6 | Number of chunks retrieved per query |
| RETRIEVAL_MIN_SCORE | No | 0.30 | Minimum cosine score to answer (below = decline) |
| YOUTUBE_API_KEY | No | — | YouTube Data API v3 (resource enrichment) |
| TAVILY_API_KEY | No | — | Tavily search API (resource enrichment) |

## Design Decisions

**Single LLM abstraction** — `LLMClient` in `app/services/llm.py` exposes `stream_chat` and `complete_json`. Every feature uses these two methods; swapping providers requires only changing env vars.

**In-memory stores with TTL eviction** — `SessionStore` and `CourseStore` use a dict + `datetime.now(UTC)` timestamps. No database dependency keeps the stack simple and portable. TTL is configurable via `SESSION_TTL_MINUTES`.

**NumPy cosine similarity** — `VectorStore` stores embeddings as a NumPy matrix and computes cosine similarity in one vectorised operation. No vector database needed for the expected session sizes.

**Blocking work off the event loop** — PDF parsing, PPTX parsing, and embedding generation all run via `asyncio.to_thread` / `run_in_threadpool` so the FastAPI event loop stays responsive.

**Decline rather than hallucinate** — If retrieval returns no chunks above `RETRIEVAL_MIN_SCORE`, the chat pipeline sets `declined=true` in the `done` SSE event and the UI shows a warning instead of a fabricated answer.

**Resource enrichment fallback chain** — `enrich_lesson` tries YouTube Data API v3 first (best quality), then Tavily (web articles), then LLM-suggested URLs as a last resort. All non-YouTube URLs are HEAD-validated before being stored.

**RFC 6901 JSON Pointer for PATCH** — The `PATCH /courses/{cid}/plan` endpoint accepts a JSON Pointer path (e.g. `/modules/0/title`) so the frontend can update any nested field without a custom schema per field.

**Offline tests** — All 137 tests run without a network connection or real API key. `FakeLLM` is scriptable (queue of responses), `FakeEmbedder` produces deterministic hash-based vectors, and `httpx.AsyncClient` is patched with `AsyncMock` for resource enrichment tests.

## Evaluation

The evaluation suite lives in `backend/eval/`:

- `make_fixtures.py` — generates a set of question/answer pairs from sample sources
- `run_eval.py` — runs each question through the RAG pipeline and scores answers for relevance and citation accuracy

Run with:

```bash
cd backend
python -m eval.make_fixtures
python -m eval.run_eval
```

## API

See [docs/API_CONTRACT.md](docs/API_CONTRACT.md) and [docs/course.schema.json](docs/course.schema.json).

## Known Limitations

- **In-memory only** — all sessions and courses are lost on server restart; no persistence layer.
- **Single-process** — the in-memory stores are not shared across multiple workers; run with a single Uvicorn worker.
- **Embedding model cold start** — `sentence-transformers` downloads the model on first run (~90 MB); subsequent starts use the local cache.
- **Resource validation latency** — HEAD-checking URLs adds latency to resource refresh; unreachable URLs are silently dropped.
- **No authentication** — session and course IDs are UUIDs but there is no auth layer; anyone with the ID can access the data.
- **YouTube transcript ingestion** — relies on `youtube-transcript-api`; videos without captions will fail ingestion.

## Demo

- Video: _TBD_
- Live: _TBD_
