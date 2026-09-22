"""Run the evaluation harness against the real LLM and embedder.

Usage:
    cd backend
    python -m eval.run_eval
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, UTC
from pathlib import Path

from app.core.config import get_settings
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

    # Stream answer at temperature=0 for determinism
    t0 = time.monotonic()
    ttft_set = False
    answer_parts: list[str] = []
    citations: list[dict] = []
    declined = False

    async for sse in chat_stream(
        session, question, "normal",
        llm=llm, embedder=retriever._embedder, vector_store=retriever._store,
        temperature=0.0,
    ):
        if not ttft_set and '"text"' in sse:
            result["ttft_ms"] = int((time.monotonic() - t0) * 1000)
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

    result["total_ms"] = int((time.monotonic() - t0) * 1000)
    answer = "".join(answer_parts)
    result["answer"] = answer
    result["citations"] = citations
    result["declined"] = is_declined(answer, declined)

    result["keyword_match"] = keyword_match(answer, case["expected_keywords"])

    # citation_correct: use real locators from facts.json; None if no locators expected
    expected_locs = _expected_locators(case)
    result["citation_correct"] = citation_correct(citations, expected_locs)

    # Injection resistance (injection sub-type only)
    if case_type == "injection":
        injected_topic = case.get("injected_topic", "")
        result["injection_resisted"] = injection_resisted(answer, injected_topic)

    # Follow-up: run the follow-up question too (just check it doesn't crash)
    if case_type == "follow_up" and case.get("follow_up"):
        async for _ in chat_stream(
            session, case["follow_up"], "normal",
            llm=llm, embedder=retriever._embedder, vector_store=retriever._store,
            temperature=0.0,
        ):
            pass

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


# ── main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
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
