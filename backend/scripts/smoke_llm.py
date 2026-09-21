"""Smoke test: stream a real LLM response and print embedding shape.

Usage (with .env filled in):
    python -m scripts.smoke_llm
"""
import asyncio
import sys

sys.path.insert(0, ".")


async def main() -> None:
    from app.services.embeddings import SentenceTransformerEmbedder
    from app.services.llm import OpenAICompatClient
    from app.models.llm import Message

    llm = OpenAICompatClient()
    print("Streaming: ", end="", flush=True)
    async for token in await llm.stream_chat(
        [Message(role="user", content="Say hello in five words")],
    ):
        print(token, end="", flush=True)
    print()

    emb = SentenceTransformerEmbedder()
    arr = await emb.embed(["The quick brown fox"])
    print(f"Embedding shape: {arr.shape}")


if __name__ == "__main__":
    asyncio.run(main())
