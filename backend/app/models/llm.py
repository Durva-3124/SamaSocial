"""LLM-related Pydantic models."""
from typing import Literal

from pydantic import BaseModel


class Message(BaseModel):
    """A single chat message."""

    role: Literal["user", "assistant"]
    content: str
