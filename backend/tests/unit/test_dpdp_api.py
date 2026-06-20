"""Tests for DPDP endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_current_user


client = TestClient(app, raise_server_exceptions=False)


def _mock_user(role="analyst"):
    user = MagicMock()
    user.id = 1
    user.role = role
    user.is_active = True
    return user


@patch("app.database.get_async_db", new_callable=AsyncMock)
def test_data_request_happy_path(mock_db):
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 5
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_db.return_value = mock_session

    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    try:
        resp = client.get("/api/v1/dpdp/data-request")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "summary" in data
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@patch("app.database.get_async_db", new_callable=AsyncMock)
def test_erasure_request_happy_path(mock_db):
    mock_db.return_value = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    try:
        resp = client.post("/api/v1/dpdp/erasure-request")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@patch("app.database.get_async_db", new_callable=AsyncMock)
def test_dpdp_register_requires_admin(mock_db):
    mock_db.return_value = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: _mock_user("analyst")
    try:
        resp = client.get("/api/v1/dpdp/register")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
