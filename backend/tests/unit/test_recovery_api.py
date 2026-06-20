"""Tests for recovery endpoints."""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_async_db


client = TestClient(app, raise_server_exceptions=False)


def _mock_db_session(existing_case=None):
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_case
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    return mock_session


def test_initiate_recovery_happy_path():
    mock_session = _mock_db_session()
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.post("/api/v1/recovery/initiate", json={
            "fraud_type": "vishing",
            "amount_lost": 5000,
            "incident_date": "2025-01-15",
            "victim_name": "Test User",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "case_id" in data
        assert data["fraud_type"] == "vishing"
        assert data["amount_lost"] == 5000
        assert len(data["steps"]) > 0
        assert "complaint_draft" in data
        assert "helpline_numbers" in data
    finally:
        app.dependency_overrides.pop(get_async_db, None)


def test_get_recovery_status_not_found():
    mock_session = _mock_db_session(existing_case=None)
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.get("/api/v1/recovery/nonexistent-id/status")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_async_db, None)


def test_get_recovery_status_found():
    case = MagicMock()
    case.current_step = 2
    case.total_steps = 6
    case.status = "in_progress"
    case.last_updated = MagicMock()
    case.last_updated.isoformat.return_value = "2025-01-15T00:00:00Z"
    mock_session = _mock_db_session(existing_case=case)
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.get("/api/v1/recovery/fake-case-id/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_step"] == 2
        assert data["total_steps"] == 6
        assert data["status"] == "in_progress"
    finally:
        app.dependency_overrides.pop(get_async_db, None)


def test_initiate_recovery_validation_error():
    resp = client.post("/api/v1/recovery/initiate", json={"fraud_type": "vishing"})
    assert resp.status_code == 422
