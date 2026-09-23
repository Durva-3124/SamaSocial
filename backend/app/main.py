"""FastAPI application entry point."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.bonus import router as bonus_router
from app.api.chat import router as chat_router
from app.api.courses import router as courses_router
from app.api.sessions import router as sessions_router
from app.core.errors import AppError, app_error_handler, unhandled_error_handler

logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(title="Samasocial AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_origin_regex=r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)
app.include_router(sessions_router)
app.include_router(chat_router)
app.include_router(bonus_router)
app.include_router(courses_router)


@app.get("/api/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}
