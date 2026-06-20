"""Tests for intel (multi-bank fraud intelligence) endpoints."""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_async_db


client = TestClient(app, raise_server_exceptions=False)


def _mock_db_session():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 0
    mock_result.scalars.return_value.first.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    return mock_session


def test_register_bank_happy_path():
    mock_session = _mock_db_session()
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.post("/api/v1/intel/register-bank", json={
            "bank_name": "Test Bank",
            "bank_code": "TST",
            "contact_email": "admin@test.com",
            "contact_name": "Admin",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "bank_id" in data
        assert "api_key" in data
        assert data["api_key"].startswith("ts_bank_")
    finally:
        app.dependency_overrides.pop(get_async_db, None)


def test_register_bank_duplicate_code():
    mock_session = _mock_db_session()
    existing = MagicMock()
    existing.bank_code = "TST"
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing
    mock_session.execute = AsyncMock(return_value=mock_result)
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.post("/api/v1/intel/register-bank", json={
            "bank_name": "Test Bank",
            "bank_code": "TST",
            "contact_email": "admin@test.com",
            "contact_name": "Admin",
        })
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_async_db, None)


def test_network_stats_requires_bank_auth():
    mock_session = _mock_db_session()
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.get("/api/v1/intel/stats")
        assert resp.status_code in (401, 422)
    finally:
        app.dependency_overrides.pop(get_async_db, None)
