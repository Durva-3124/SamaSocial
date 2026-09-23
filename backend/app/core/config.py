"""Centralised application settings loaded from .env."""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from here. Never read os.environ elsewhere."""

    # LLM
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""

    # Embeddings
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # CORS
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # Limits
    MAX_UPLOAD_MB: int = 25
    SESSION_TTL_MINUTES: int = 120

    # Retrieval
    RETRIEVAL_TOP_K: int = 6
    RETRIEVAL_MIN_SCORE: float = 0.30

    # Optional third-party keys
    YOUTUBE_API_KEY: Optional[str] = None
    YOUTUBE_PROXY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
