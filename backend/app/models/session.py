"""Session and source record models."""
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.chunk import SourceType
from app.models.llm import Message


class SourceRecord(BaseModel):
    """Tracks the state of an ingested source within a session."""

    id: str
    type: SourceType
    name: str
    status: Literal["processing", "ready", "failed"] = "processing"
    error: str | None = None
    chunk_count: int = 0
    summary: str | None = None
    topics: list[str] = []
    warnings: list[str] = []


class Session(BaseModel):
    """An in-memory learning session."""

    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sources: dict[str, SourceRecord] = {}
    history: list[Message] = []
