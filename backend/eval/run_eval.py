"""Run the evaluation harness against the real LLM and embedder.

Usage:
    cd backend
    python -m eval.run_eval
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, UTC
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.session import Session, SourceRecord
from app.services.embeddings import get_embedder
from app.services.ingestion.pdf import ingest_pdf
from app.services.ingestion.pptx import ingest_pptx
from app.services.ingestion.youtube import group_transcript
from app.services.ingestion.web import _split_by_headings
from app.services.llm import get_llm
from app.services.retrieval import Retriever
from app.services.stores.vector_store import VectorStore
from app.services.chunking import split_text
from app.models.chunk import Chunk, Locator

from eval.dataset import CASES
from eval.fixtures import (
    build_ml_html,
    build_python_transcript,
    FACTS,
)
from eval.scoring import (
    citation_correct,
    cross_source_retrieval_hit,
    injection_resisted,
    is_declined,
    keyword_match,
    retrieval_hit,
    score_summary,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPORT_PATH = Path(__file__).parent / "report.md"

# Build a lookup dict from facts.json for citation locator resolution
_FACTS_BY_ID: dict[str, dict] = {f["id"]: f for f in FACTS}


def _expected_locators(case: dict) -> list[str]:
    """Return the expected locator strings for a case from facts.json."""
    return [
        _FACTS_BY_ID[fid]["locator"]
        for fid in case.get("expected_fact_ids", [])
        if fid in _FACTS_BY_ID
    ]


def _parse_retry_after(exc: Exception) -> float:
    """Parse the retry_after value from AppError or exception message."""
    if hasattr(exc, "retry_after") and isinstance(getattr(exc, "retry_after"), (int, float)):
        return float(getattr(exc, "retry_after"))
    msg = getattr(exc, "message", "") or str(exc)
    match = re.search(r"Retry after (\d+(?:\.\d+)?)s?", msg, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return 15.0


def _is_rate_limit(exc: Exception) -> bool:
    """Check if exception represents a rate limit error."""
    if isinstance(exc, AppError) and exc.code == "LLM_RATE_LIMIT":
        return True
    msg = (getattr(exc, "message", "") or str(exc)).lower()
    return "rate limit" in msg or "429" in msg


# ── ingestion helpers (no HTTP — feed bytes/strings directly) ─────────────────

def _ingest_html_direct(source_id: str, html: str) -> list[Chunk]:
    """Ingest HTML string without fetching — reuses web.py's splitter."""
    import re
    import trafilatura
    markdown = trafilatura.extract(html, output_format="markdown", include_tables=True) or ""
    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    page_title = title_match.group(1).strip() if title_match else "ML Basics"
    sections = _split_by_headings(markdown)
    chunks: list[Chunk] = []
    for heading, body in sections:
        if not body.strip():
            continue
        for piece in split_text(body):
            chunks.append(Chunk(
                source_id=source_id,
                source_type="web",
                text=piece,
                locator=Locator(heading=heading or page_title),
            ))
    return chunks


def _ingest_transcript_direct(source_id: str, entries: list[dict]) -> list[Chunk]:
    """Ingest transcript entries without YouTube API."""
    groups = group_transcript(entries)
    chunks: list[Chunk] = []
    for start_sec, text in groups:
        for piece in split_text(text):
            chunks.append(Chunk(
                source_id=source_id,
                source_type="youtube",
                text=piece,
                locator=Locator(start_seconds=start_sec),
            ))
    return chunks


# ── session setup ─────────────────────────────────────────────────────────────

async def build_session(embedder, vector_store: VectorStore) -> tuple[Session, dict[str, str]]:
    """Ingest all four fixtures into a fresh session. Returns (session, source_map)."""
    session = Session(id="eval-session")
    source_map: dict[str, str] = {}  # source_type -> source_id

    async def _add(source_id: str, source_type: str, name: str, chunks: list[Chunk]) -> None:
        texts = [c.text for c in chunks]
        embeddings = await embedder.embed(texts)
        vector_store.add(session.id, chunks, embeddings)
        session.sources[source_id] = SourceRecord(
            id=source_id, type=source_type, name=name, status="ready",
            chunk_count=len(chunks),
        )
        source_map[source_type] = source_id

    pdf_path = FIXTURES_DIR / "photosynthesis.pdf"
    pdf_result = ingest_pdf("src-pdf", "photosynthesis.pdf", pdf_path.read_bytes())
    await _add("src-pdf", "pdf", "Photosynthesis", pdf_result.chunks)

    pptx_path = FIXTURES_DIR / "rest_apis.pptx"
    pptx_result = ingest_pptx("src-pptx", "rest_apis.pptx", pptx_path.read_bytes())
    await _add("src-pptx", "pptx", "REST APIs", pptx_result.chunks)

    html_chunks = _ingest_html_direct("src-web", build_ml_html())
    await _add("src-web", "web", "ML Basics", html_chunks)

    transcript_chunks = _ingest_transcript_direct("src-yt", build_python_transcript())
    await _add("src-yt", "youtube", "Python Tutorial", transcript_chunks)

    print(f"  Session built: {sum(s.chunk_count for s in session.sources.values())} total chunks")
    return session, source_map


# ── single case runner ────────────────────────────────────────────────────────

async def run_case(
    case: dict,
    session: Session,
    retriever: Retriever,
    llm,
) -> dict:
    """Run one eval case and return a result dict."""
    from app.services.chat import chat_stream

    question = case["question"]
    case_type = case["type"]
    result: dict = {
        "id": case["id"],
        "type": case_type,
        "question": question,
        "answer": "",
        "citations": [],
        "declined": False,
        "keyword_match": False,
        "citation_correct": None,  # None = N/A
        "retrieval_hit": False,
        "injection_resisted": None,  # None = N/A
        "ttft_ms": 0,
        "total_ms": 0,
    }

    # Retrieve for hit scoring (independent of LLM)
    retrieved = await retriever.retrieve(session.id, question, top_k=6, min_score=0.0)
    retrieved_chunks = [{"text": c.text} for c, _ in retrieved]

    if case_type == "cross_source":
        hit, missing = cross_source_retrieval_hit(
            retrieved_chunks, case["expected_fact_ids"], _FACTS_BY_ID
        )
        result["retrieval_hit"] = hit
        if missing:
            print(f"         cross_source miss — sources not retrieved: {missing}")
    else:
        result["retrieval_hit"] = retrieval_hit(retrieved_chunks, case["expected_keywords"])

    # Stream answer at temperature=0 for determinism, with rate-limit retry
    max_retries = 2
    retries_used = 0

    async def _run_chat_stream() -> tuple[str, list[dict], bool, int, int]:
        """Run chat_stream and return (answer, citations, declined, ttft_ms, total_ms)."""
        t0 = time.monotonic()
        ttft_set = False
        answer_parts: list[str] = []
        citations: list[dict] = []
        declined = False
        ttft_ms = 0

        async for sse in chat_stream(
            session, question, "normal",
            llm=llm, embedder=retriever._embedder, vector_store=retriever._store,
            temperature=0.0,
        ):
            if not ttft_set and '"text"' in sse:
                ttft_ms = int((time.monotonic() - t0) * 1000)
                ttft_set = True
            if sse.startswith("event: token"):
                data = json.loads(sse.split("data: ", 1)[1])
                answer_parts.append(data.get("text", ""))
            elif sse.startswith("event: citations"):
                data = json.loads(sse.split("data: ", 1)[1])
                citations = data.get("items", [])
            elif sse.startswith("event: done"):
                data = json.loads(sse.split("data: ", 1)[1])
                declined = data.get("declined", False)
            elif sse.startswith("event: error"):
                # Check if it's a rate limit error — if so, raise to trigger retry
                data = json.loads(sse.split("data: ", 1)[1])
                if data.get("code") == "LLM_RATE_LIMIT":
                    from app.core.errors import AppError
                    raise AppError("LLM_RATE_LIMIT", data.get("message", "Rate limited"), 502)

        total_ms = int((time.monotonic() - t0) * 1000)
        return "".join(answer_parts), citations, declined, ttft_ms, total_ms

    while retries_used <= max_retries:
        try:
            answer, citations, declined, ttft_ms, total_ms = await _run_chat_stream()
            result["answer"] = answer
            result["citations"] = citations
            result["declined"] = is_declined(answer, declined)
            result["ttft_ms"] = ttft_ms
            result["total_ms"] = total_ms
            break
        except Exception as exc:
            if _is_rate_limit(exc) and retries_used < max_retries:
                retries_used += 1
                wait_sec = _parse_retry_after(exc) + 2.0
                print(f"       [rate-limited, sleeping {wait_sec:.1f}s (retry {retries_used}/{max_retries})]")
                await asyncio.sleep(wait_sec)
                continue
            # Not a rate limit, or retries exhausted — record failure and continue
            if _is_rate_limit(exc):
                print(f"       [rate limit retries exhausted, marking case as rate-limited]")
                result["answer"] = ""
                result["citations"] = []
                result["declined"] = False
                result["ttft_ms"] = 0
                result["total_ms"] = 0
                result["rate_limited"] = True
            else:
                raise
            break

    result["keyword_match"] = keyword_match(result["answer"], case["expected_keywords"])

    # citation_correct: use real locators from facts.json; None if no locators expected
    expected_locs = _expected_locators(case)
    result["citation_correct"] = citation_correct(result["citations"], expected_locs)

    # Injection resistance (injection sub-type only)
    if case_type == "injection":
        injected_topic = case.get("injected_topic", "")
        result["injection_resisted"] = injection_resisted(result["answer"], injected_topic)

    # Follow-up: run the follow-up question too (just check it doesn't crash)
    if case_type == "follow_up" and case.get("follow_up"):
        # Follow-up also needs retry logic
        retries_used = 0
        while retries_used <= max_retries:
            try:
                async for _ in chat_stream(
                    session, case["follow_up"], "normal",
                    llm=llm, embedder=retriever._embedder, vector_store=retriever._store,
                    temperature=0.0,
                ):
                    pass
                break
            except Exception as exc:
                if _is_rate_limit(exc) and retries_used < max_retries:
                    retries_used += 1
                    wait_sec = _parse_retry_after(exc) + 2.0
                    print(f"       [rate-limited on follow-up, sleeping {wait_sec:.1f}s (retry {retries_used}/{max_retries})]")
                    await asyncio.sleep(wait_sec)
                    continue
                # Not a rate limit, or retries exhausted — just log and continue
                print(f"       [follow-up failed: {exc}]")
                break

    return result


# ── report writer ─────────────────────────────────────────────────────────────

def write_report(results: list[dict], summary: dict, settings) -> None:
    ttfts = [r["ttft_ms"] for r in results if r["ttft_ms"] > 0]
    totals = [r["total_ms"] for r in results if r["total_ms"] > 0]
    median_ttft = sorted(ttfts)[len(ttfts) // 2] if ttfts else 0
    p95_ttft = sorted(ttfts)[int(len(ttfts) * 0.95)] if ttfts else 0
    median_total = sorted(totals)[len(totals) // 2] if totals else 0

    lines = [
        "# Evaluation Report",
        f"\nDate: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Model: `{settings.LLM_MODEL}`",
        f"Cases: {len(results)}",
        "",
        "## Metrics by Case Type",
        "",
        "| Type | N | keyword_match | citation_correct | retrieval_hit | decline_rate |",
        "|---|---|---|---|---|---|",
    ]
    for case_type, m in summary.items():
        decline = m.get("decline_rate")
        decline_str = "N/A" if decline is None else f"{decline:.0%}"
        cit = m.get("citation_correct")
        cit_str = "N/A" if cit is None else f"{cit:.0%}"
        lines.append(
            f"| {case_type} | {m['count']} "
            f"| {m['keyword_match']:.0%} "
            f"| {cit_str} "
            f"| {m['retrieval_hit']:.0%} "
            f"| {decline_str} |"
        )

    lines += [
        "",
        "## Latency",
        "",
        f"- Median TTFT: {median_ttft} ms",
        f"- p95 TTFT: {p95_ttft} ms",
        f"- Median total: {median_total} ms",
        "",
        "## Failing Cases",
        "",
    ]

    failing = [
        r for r in results
        if not r["keyword_match"] and r["type"] not in ("out_of_scope", "false_premise", "injection")
    ]
    if not failing:
        lines.append("_All in-scope cases passed keyword match._")
    else:
        for r in failing:
            lines += [
                f"### {r['id']} ({r['type']})",
                f"**Q:** {r['question']}",
                f"**A:** {r['answer'][:300]}...",
                f"**Retrieved locators:** {[c.get('locator_text') for c in r['citations']]}",
                "",
            ]

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {REPORT_PATH}")


# ── pdf debug (c01-c05 only) ──────────────────────────────────────────────────

async def run_pdf_debug() -> None:
    """Run only c01-c05 and print retrieval/citation/expected side-by-side."""
    from app.services.chat import chat_stream
    from eval.scoring import normalise

    embedder = get_embedder()
    llm = get_llm()
    vector_store = VectorStore()

    print("Building session from fixtures...")
    session, _ = await build_session(embedder, vector_store)
    retriever = Retriever(embedder=embedder, store=vector_store)

    pdf_cases = [c for c in CASES if c["id"] in {"c01", "c02", "c03", "c04", "c05"}]

    for case in pdf_cases:
        print(f"\n{'='*70}")
        print(f"Case {case['id']}: {case['question']}")

        # (a) full top-k retrieval with locators
        retrieved = await retriever.retrieve(session.id, case["question"], top_k=6, min_score=0.0)
        print(f"\n  (a) Retrieved top-{len(retrieved)} chunks (rank, locator_text, score):")
        for rank, (chunk, score) in enumerate(retrieved, 1):
            print(f"      [S{rank}] {chunk.locator_text()!r:30s}  score={score:.4f}")

        # (b) stream and capture which [S#] tags the model used
        answer_parts: list[str] = []
        citations: list[dict] = []
        async for sse in chat_stream(
            session, case["question"], "normal",
            llm=llm, embedder=retriever._embedder, vector_store=retriever._store,
            temperature=0.0,
        ):
            if sse.startswith("event: token"):
                answer_parts.append(json.loads(sse.split("data: ", 1)[1]).get("text", ""))
            elif sse.startswith("event: citations"):
                citations = json.loads(sse.split("data: ", 1)[1]).get("items", [])

        print(f"\n  (b) Model-cited chunks (label -> locator_text -> normalised):")
        cited_normalised: set[str] = set()
        for c in citations:
            raw = c.get("locator_text", "")
            norm = normalise(raw)
            cited_normalised.add(norm)
            print(f"      [{c['label']}] raw={raw!r:30s}  normalised={norm!r}")
        if not citations:
            print("      (no citations emitted)")

        # (c) expected locators and whether they appear in retrieval or citations
        expected_locs = _expected_locators(case)
        retrieved_locs_norm = {normalise(chunk.locator_text()) for chunk, _ in retrieved}
        print(f"\n  (c) Expected locators from facts.json:")
        for exp in expected_locs:
            norm_exp = normalise(exp)
            in_retrieval = norm_exp in retrieved_locs_norm
            in_citations = norm_exp in cited_normalised
            print(f"      raw={exp!r:30s}  normalised={norm_exp!r}")
            print(f"           in_retrieval={in_retrieval}  in_citations={in_citations}")
            if not in_retrieval:
                print(f"           *** RETRIEVAL MISS — expected locator not in top-k ***")
            elif not in_citations:
                print(f"           *** CITATION MISS — retrieved but model did not cite it ***")

        await asyncio.sleep(5)


# ── main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    import sys
    if "--pdf-debug" in sys.argv:
        await run_pdf_debug()
        return

    settings = get_settings()
    print(f"Model: {settings.LLM_MODEL}")

    embedder = get_embedder()
    llm = get_llm()
    vector_store = VectorStore()

    print("Building session from fixtures...")
    session, _ = await build_session(embedder, vector_store)

    retriever = Retriever(embedder=embedder, store=vector_store)

    print(f"Running {len(CASES)} eval cases...")
    results: list[dict] = []
    for i, case in enumerate(CASES, 1):
        print(f"  [{i:02d}/{len(CASES)}] {case['id']} ({case['type']}) -- {case['question'][:60]}")
        r = await run_case(case, session, retriever, llm)
        results.append(r)
        kw_ok = r["keyword_match"] or case["type"] in ("out_of_scope", "false_premise", "injection")
        status = "PASS" if kw_ok else "FAIL"
        print(f"         {status} | ttft={r['ttft_ms']}ms | declined={r['declined']}")
        await asyncio.sleep(5)  # stay within free-tier RPM

    summary = score_summary(results)

    print("\n-- Summary " + "-" * 49)
    print(f"{'Type':<15} {'N':>4} {'kw_match':>10} {'cit_ok':>8} {'ret_hit':>9} {'decline':>9}")
    print("-" * 60)
    for case_type, m in summary.items():
        cit = m.get("citation_correct")
        cit_str = " N/A" if cit is None else f"{cit:9.0%}"
        print(
            f"{case_type:<15} {m['count']:>4} "
            f"{m['keyword_match']:>9.0%} "
            f"{cit_str:>8} "
            f"{m['retrieval_hit']:>9.0%} "
            f"{m.get('decline_rate', 0):>9.0%}"
        )

    write_report(results, summary, settings)


if __name__ == "__main__":
    asyncio.run(main())
