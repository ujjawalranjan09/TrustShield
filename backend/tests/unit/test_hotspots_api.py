"""Tests for hotspots endpoint."""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_async_db


client = TestClient(app, raise_server_exceptions=False)


def _mock_db_session(rows=None):
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = rows or []
    mock_result.scalar.return_value = 0
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


def test_hotspots_empty():
    mock_session = _mock_db_session()
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.get("/api/v1/analytics/hotspots")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_source"] == "empty"
        assert data["total_regions"] == 0
        assert data["hotspots"] == []
    finally:
        app.dependency_overrides.pop(get_async_db, None)


def test_hotspots_with_data():
    row = MagicMock()
    row.region = "Mumbai"
    row.count = 60
    row.top_type = "vishing"
    row.avg_lat = 19.0760
    row.avg_lng = 72.8777
    mock_session = _mock_db_session(rows=[row])
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.get("/api/v1/analytics/hotspots?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_source"] == "flagged_entities"
        assert data["total_regions"] == 1
        assert data["hotspots"][0]["region"] == "Mumbai"
        assert data["hotspots"][0]["risk_level"] == "high"
    finally:
        app.dependency_overrides.pop(get_async_db, None)


def test_hotspots_validation_days_range():
    resp = client.get("/api/v1/analytics/hotspots?days=100")
    assert resp.status_code == 422
