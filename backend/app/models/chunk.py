"""Chunk and Locator models shared across all ingestors."""
import uuid
from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal["pdf", "pptx", "youtube", "web"]


class Locator(BaseModel):
    """Points to the exact location of a chunk within its source."""

    page: int | None = None
    slide: int | None = None
    start_seconds: int | None = None
    heading: str | None = None


class Chunk(BaseModel):
    """A single retrievable unit of text from a source."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    source_id: str
    source_type: SourceType
    text: str
    locator: Locator

    def locator_text(self) -> str:
        """Return a human-readable location string for citations."""
        if self.locator.page is not None:
            return f"page {self.locator.page}"
        if self.locator.slide is not None:
            return f"slide {self.locator.slide}"
        if self.locator.start_seconds is not None:
            s = self.locator.start_seconds
            if s >= 3600:
                h, rem = divmod(s, 3600)
                m, sec = divmod(rem, 60)
                return f"at {h}:{m:02d}:{sec:02d}"
            m, sec = divmod(s, 60)
            return f"at {m}:{sec:02d}"
        if self.locator.heading:
            return f'section "{self.locator.heading}"'
        return ""
