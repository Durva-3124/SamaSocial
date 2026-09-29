# API Contract

Base path `/api`. JSON everywhere except SSE endpoints.
Errors: HTTP status + `{"error": {"code": "STRING", "message": "human readable"}}`.
SSE: `Content-Type: text/event-stream`; each event is `event: <name>\ndata: <json>\n\n`.

## Task 1: Learning Assistant

| Endpoint | Request | Response |
|---|---|---|
| `POST /sessions` | none | `201 {"session_id"}` |
| `POST /sessions/{sid}/sources/file` | multipart field `file` (.pdf/.pptx, max MAX_UPLOAD_MB) | `202 {"source_id","status":"processing"}` |
| `POST /sessions/{sid}/sources/url` | `{"url"}` (YouTube auto-detected, else webpage) | `202 {"source_id","status":"processing","type":"youtube|web"}` |
| `GET /sessions/{sid}/sources` | none | `200 {"sources":[{"id","type":"pdf|pptx|youtube|web","name","status":"processing|ready|failed","error":null|"msg","chunk_count":int,"summary":null|"text","topics":[str],"warnings":[str]}]}` |
| `DELETE /sessions/{sid}/sources/{source_id}` | none | `204` |
| `GET /sources/accept` | none | `200 {"extensions":["pdf","pptx"],"accept":".pdf,.pptx","description":str}` |
| `POST /sessions/{sid}/chat` | `{"message","mode":"normal|simple"}` | SSE (below) |
| `POST /sessions/{sid}/quiz` | `{"num_questions":5,"source_ids":null|[..]}` | `200 {"questions":[{"question","options":[4 strings],"answer_index":0-3,"explanation","source_id","locator_text"}]}` |

Chat SSE events:
- `token` `{"text"}`
- `citations` `{"items":[{"label":"S1","source_id","source_name","source_type","locator":{...},"locator_text":"slide 4","snippet"}]}`
- `done` `{"declined":bool,"used_source_ids":[..]}`
- `error` `{"code","message"}`

File uploads are limited by `MAX_UPLOAD_MB` and to eight sources per session.
The backend validates extension, declared MIME type, and file signature. URL
uploads are limited to HTTP(S) public destinations and are classified by exact
YouTube host; duplicate URLs are rejected. A duplicate filename is rejected
only while the matching source is still processing.

## Task 2: Course Planner

| Endpoint | Request | Response |
|---|---|---|
| `POST /courses` | none | `201 {"course_id"}` |
| `GET /courses/{cid}` | none | `200 {"intake":{..},"missing":[..],"plan":Course|null,"plan_version":int,"messages":[{"role","content"}]}` |
| `POST /courses/{cid}/chat` | `{"message"}` | SSE (below) |
| `PATCH /courses/{cid}/plan` | `{"path":"/modules/0/title","value":<json>}` (JSON Pointer, RFC 6901) | `200 {"plan":Course,"plan_version":int}` |
| `GET /courses/{cid}/export` | none | `application/json` attachment |
| `POST /courses/{cid}/syllabus[?replace=true]` | multipart field `file` (.pdf) | SSE (`intake_state`, `plan_update`, `token`, `done`; or `error`) |
| `POST /courses/{cid}/resources/refresh` | `{"lesson_id":null|"m1-l2"}` | SSE (`plan_update`, `resources_unavailable`, `done`; or `error`) |

Course chat SSE events:
- `token` `{"text"}`
- `intake_state` `{"intake":{..},"missing":[..]}`
- `plan_update` `{"plan":Course,"plan_version":int,"changed_ids":[..]}`
- `done` `{}`
- `error` `{"code","message"}`

Resource-refresh SSE events:
- `plan_update` `{"plan":Course,"plan_version":int,"changed_ids":[..]}`
- `resources_unavailable` `{"reason"}` when neither resource API key is configured
- `done` `{}`
- `error` `{"code","message"}`

The current frontend sends PATCH updates for course title/description, module
title, and lesson title. The backend also whitelists additional paths, but its
allowlist currently includes module/lesson fields absent from the `Course`
Pydantic model (for example module `assessment` and lesson `practice`); those
values can be discarded by model validation. Treat such paths as unsupported
until the allowlist and model are reconciled. Syllabus upload replaces an
existing plan only when `replace=true`; it is PDF-only and subject to the
configured upload-size limit.
