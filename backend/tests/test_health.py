"""Tests for the health endpoint."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    """GET /api/health returns 200 with status ok, version, and uptime."""
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert isinstance(body["uptime_seconds"], float)


def test_app_error_handler() -> None:
    """AppError is serialised to the contract shape."""
    from app.core.errors import AppError

    @app.get("/api/test-error")
    async def _raise() -> None:
        raise AppError("TEST_CODE", "test message", 418)

    response = client.get("/api/test-error")
    assert response.status_code == 418
    assert response.json() == {"error": {"code": "TEST_CODE", "message": "test message"}}
