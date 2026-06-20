"""Tests for report and lookup endpoints."""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_async_db


client = TestClient(app, raise_server_exceptions=False)


def _mock_db_session(existing_entity=None):
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_entity
    mock_result.scalar.return_value = 0
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    return mock_session


def test_report_entity_happy_path():
    mock_session = _mock_db_session()
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.post("/api/v1/report", json={
            "entity_value": "+919876543210",
            "entity_type": "PHONE",
            "scam_type": "vishing",
            "description": "Suspicious call",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "report_id" in data
        assert data["status"] in ("pending", "confirmed")
        assert "message" in data
    finally:
        app.dependency_overrides.pop(get_async_db, None)


def test_lookup_entity_not_found():
    mock_session = _mock_db_session(existing_entity=None)
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.get("/api/v1/lookup/PHONE/9999999999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_flagged"] is False
        assert data["report_count"] == 0
    finally:
        app.dependency_overrides.pop(get_async_db, None)


def test_lookup_entity_found():
    entity = MagicMock()
    entity.entity_value = "PHONE:+919876543210"
    entity.entity_type = "PHONE"
    entity.is_confirmed = 1
    entity.report_count = 5
    entity.first_reported = MagicMock()
    entity.first_reported.isoformat.return_value = "2025-01-01T00:00:00Z"
    entity.last_seen = MagicMock()
    entity.last_seen.isoformat.return_value = "2025-01-15T00:00:00Z"
    mock_session = _mock_db_session(existing_entity=entity)
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.get("/api/v1/lookup/PHONE/9876543210")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_flagged"] is True
        assert data["risk_level"] == "high"
    finally:
        app.dependency_overrides.pop(get_async_db, None)


def test_report_stats_happy_path():
    mock_session = _mock_db_session()
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.get("/api/v1/reports/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_entities_reported" in data
        assert "total_reports" in data
        assert "confirmed_fraudsters" in data
    finally:
        app.dependency_overrides.pop(get_async_db, None)
