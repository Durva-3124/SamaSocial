"""Base types for all ingestors."""
from typing import Protocol

from pydantic import BaseModel

from app.models.chunk import Chunk, SourceType


class IngestResult(BaseModel):
    """Output of any ingestor."""

    name: str
    source_type: SourceType
    chunks: list[Chunk]
    warnings: list[str] = []


class Ingestor(Protocol):
    """Synchronous ingestor interface (run in a thread via asyncio.to_thread)."""

    def ingest(self, *args, **kwargs) -> IngestResult: ...
