# Samasocial AI

## Overview

## Features

### Task 1: Learning Assistant

### Task 2: Course Planner

## Architecture

## Setup

### Prerequisites

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

## Evaluation

## API

See [docs/API_CONTRACT.md](docs/API_CONTRACT.md) and [docs/course.schema.json](docs/course.schema.json).

## Known Limitations

## Demo

- Video: _TBD_
- Live: _TBD_
