"""Tests for the health endpoint."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    """GET /api/health returns 200 with status ok."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_error_handler() -> None:
    """AppError is serialised to the contract shape."""
    from app.core.errors import AppError

    @app.get("/api/test-error")
    async def _raise() -> None:
        raise AppError("TEST_CODE", "test message", 418)

    response = client.get("/api/test-error")
    assert response.status_code == 418
    assert response.json() == {"error": {"code": "TEST_CODE", "message": "test message"}}
