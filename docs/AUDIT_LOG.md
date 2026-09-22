# Audit Log

## M16 — 2026-09-21 (Amazon Q automated audit)

**Auditor:** Amazon Q static + dynamic analysis  
**Scope:** M0–M16 complete (backend + frontend + eval harness)

### Findings resolved in this session

| ID | Sev | Description | Resolution |
|---|---|---|---|
| F02 | P0 | `stream_chat` retry logic swallowed second 429 instead of raising `LLM_RATE_LIMIT` | Fixed: added `except AppError: raise` guard; removed unused `tokens_yielded` variable |
| F03 | P1 | Frontend `Course`/`Lesson`/`IntakeData` types diverged from backend Pydantic models | Fixed: aligned `courses.ts` types exactly with `app/models/course.py` |
| F04 | P1 | `docs/LIMITATIONS.md`, `docs/DECISIONS.md`, `docs/AUDIT_LOG.md` missing | Fixed: created all three files |
| F07 | P2 | `session_store.py` TOCTOU: `last_active` updated outside lock | Fixed: moved update inside `with self._lock` block |
| F10 | P2 | Polling never stopped when all sources settled | Fixed: `useSession` stops interval when `sources.every(s => s.status !== "processing")` |
| F11 | P2 | `assistantIdx` stale closure in `useChat` and `useCourse` | Fixed: captured inside `setMessages` functional updater |
| F12 | P2 | No stream cleanup on unmount in `useChat` / `useCourse` | Fixed: `readerRef` + `useEffect` cleanup cancels in-flight reader |
| F13 | P2 | `patch()` could overwrite newer plan with stale PATCH response | Fixed: `planVersionRef` guards both `plan_update` SSE and `patch()` response |

### Findings confirmed as already resolved (audit report was stale)

| ID | Sev | Description | Status |
|---|---|---|---|
| F01 | P0 | `FakeLLM.stream_chat` protocol mismatch | Already correct — `fakes.py` uses `yield`, is a proper async generator |
| F05 | P1 | `bonus.py` accessed `vs._data` directly | Already fixed — uses `vs.all_chunks()` public API |
| F06 | P1 | `run_eval.py` `citation_correct` tautologically True | Already fixed — `_expected_locators()` resolves from `facts.json` |
| F08 | P2 | PATCH allowed writing to `id` fields | Already fixed — `plan_ops.py` whitelist excludes all `id` paths |
| F09 | P2 | `resources.py` LLM stub authored URLs | Already fixed — LLM is not called in `resources.py`; only YouTube API and Tavily |

### Open findings (P2/P3, deferred)

| ID | Sev | Description | Decision |
|---|---|---|---|
| F14 | P3 | `citation_correct` substring match could false-positive on "page 1" vs "page 10" | Deferred — `scoring.py` uses exact set membership (`in cited`), not substring; risk is low |
