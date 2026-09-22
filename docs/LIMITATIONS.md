# Known Limitations

## In-memory only
All sessions and courses are lost on server restart. There is no persistence layer (no database, no disk cache). This is intentional for simplicity and portability.

## Single-process
The in-memory `SessionStore` and `CourseStore` are not shared across multiple workers. Run with a single Uvicorn worker (`uvicorn app.main:app --workers 1`).

## Embedding model cold start
`sentence-transformers` downloads the model on first run (~90 MB). Subsequent starts use the local cache (`~/.cache/huggingface`).

## Resource validation latency
HEAD-checking URLs adds latency to resource refresh. Unreachable URLs are silently dropped. If both `YOUTUBE_API_KEY` and `TAVILY_API_KEY` are absent, resource enrichment returns a `resources_unavailable` SSE event and no resources are attached.

## No authentication
Session and course IDs are UUIDs but there is no auth layer. Anyone who knows an ID can read or modify that session/course.

## YouTube transcript ingestion
Relies on `youtube-transcript-api`. Videos without auto-generated or manual captions will fail ingestion with an `INGEST_ERROR`.

## Cross-source retrieval
The cosine similarity retrieval is per-session and does not guarantee that chunks from multiple sources are returned for cross-source questions. Retrieval quality depends on the embedding model and chunk overlap.

## Eval harness requires live API key
`eval/run_eval.py` calls the real LLM and embedder. It cannot run offline. The offline test suite (`pytest`) uses `FakeLLM` and `FakeEmbedder` and requires no API key.
