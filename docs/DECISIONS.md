# Design Decisions

## Single LLM abstraction
`LLMClient` in `app/services/llm.py` exposes `stream_chat`, `complete`, and `complete_json`. Every feature uses these three methods. Swapping providers requires only changing `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` in `.env`.

## In-memory stores with TTL eviction
`SessionStore` and `CourseStore` use a `dict` + `datetime.now(UTC)` timestamps. No database dependency keeps the stack simple and portable. TTL is configurable via `SESSION_TTL_MINUTES`.

## NumPy cosine similarity
`VectorStore` stores embeddings as a NumPy matrix and computes cosine similarity in one vectorised operation (`vecs @ query_vec`). No vector database is needed for the expected session sizes (hundreds of chunks per session).

## Blocking work off the event loop
PDF parsing, PPTX parsing, and embedding generation all run via `asyncio.to_thread` / `run_in_threadpool` so the FastAPI event loop stays responsive during ingestion.

## Decline rather than hallucinate
If retrieval returns no chunks above `RETRIEVAL_MIN_SCORE`, the chat pipeline sets `declined=true` in the `done` SSE event and the UI shows a warning instead of a fabricated answer.

## Resource enrichment fallback chain
`enrich_lesson` tries YouTube Data API v3 first (best quality), then Tavily (web articles). The LLM never authors URLs — all URLs come from API responses. Non-YouTube URLs are HEAD-validated before being stored.

## RFC 6901 JSON Pointer for PATCH
`PATCH /courses/{cid}/plan` accepts a JSON Pointer path (e.g. `/modules/0/title`) so the frontend can update any nested field without a custom schema per field. A whitelist in `plan_ops.py` restricts which paths are editable; `id` fields are immutable.

## Offline tests
All 137 tests run without a network connection or real API key. `FakeLLM` is scriptable (queue of responses), `FakeEmbedder` produces deterministic hash-based vectors, and `httpx` is patched with `AsyncMock` for resource enrichment tests.

## SSE for all streaming
Both chat pipelines (Task 1 and Task 2) use Server-Sent Events over a single HTTP response. This avoids WebSocket complexity while supporting incremental token delivery and structured events (`token`, `citations`, `done`, `plan_update`, `intake_state`).

## Whitelist-gated PATCH
`apply_patch` in `plan_ops.py` uses a compiled regex whitelist of editable pointer patterns. Any path not on the whitelist (including all `id` fields) returns 422 `FIELD_NOT_EDITABLE`. This prevents accidental or malicious corruption of structural IDs.
