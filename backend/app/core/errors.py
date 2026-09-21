"""Application error class and FastAPI exception handler."""
from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Structured application error that maps to an HTTP response."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Return a consistent {error: {code, message}} JSON response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
