"""Debug specific eval cases to see raw model responses."""
import asyncio
import sys
from eval.run_eval import build_session, run_case
from eval.dataset import CASES
from app.services.embeddings import get_embedder
from app.services.llm import get_llm
from app.services.retrieval import Retriever
from app.services.stores.vector_store import VectorStore


def _safe_print(text: str) -> None:
    """Print text safely handling encoding issues."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Replace non-encodable characters
        print(text.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8'))


async def run_specific():
    from app.core.config import get_settings
    settings = get_settings()
    _safe_print(f"Model: {settings.LLM_MODEL}")

    embedder = get_embedder()
    llm = get_llm()
    vector_store = VectorStore()

    _safe_print("Building session...")
    session, _ = await build_session(embedder, vector_store)
    retriever = Retriever(embedder=embedder, store=vector_store)

    target_ids = {"c27", "c31", "c32", "c34"}
    target_cases = [c for c in CASES if c["id"] in target_ids]

    for i, case in enumerate(target_cases):
        if i > 0:
            _safe_print("  Sleeping 30s between cases to respect rate limits...")
            await asyncio.sleep(30)
        _safe_print(f"\n{'='*70}")
        _safe_print(f"Case {case['id']} ({case['type']}): {case['question']}")
        if "note" in case:
            _safe_print(f"NOTE: {case['note']}")
        _safe_print(f"Expected keywords: {case['expected_keywords']}")
        _safe_print(f"Expected fact_ids: {case['expected_fact_ids']}")

        result = await run_case(case, session, retriever, llm)

        _safe_print(f"\n--- RESULT ---")
        _safe_print(f"Answer: {result['answer']}")
        _safe_print(f"Citations: {result['citations']}")
        _safe_print(f"Declined: {result['declined']}")
        _safe_print(f"Keyword match: {result['keyword_match']}")
        _safe_print(f"Citation correct: {result['citation_correct']}")
        _safe_print(f"Retrieval hit: {result['retrieval_hit']}")
        _safe_print(f"TTFT: {result['ttft_ms']}ms, Total: {result['total_ms']}ms")


if __name__ == "__main__":
    asyncio.run(run_specific())