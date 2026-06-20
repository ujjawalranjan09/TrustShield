"""Tests for tenant management API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_current_user
from app.database import get_async_db


client = TestClient(app, raise_server_exceptions=False)


def _mock_user(role="analyst"):
    user = MagicMock()
    user.id = 1
    user.role = role
    user.is_active = True
    return user


def _mock_db_session(existing_tenant=None):
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_tenant
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    return mock_session


def test_provision_requires_super_admin():
    app.dependency_overrides[get_current_user] = lambda: _mock_user("admin")
    app.dependency_overrides[get_async_db] = lambda: _mock_db_session()
    try:
        resp = client.post("/api/v1/tenant/provision", json={
            "slug": "test-bank",
            "display_name": "Test Bank",
        })
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_async_db, None)


@patch("app.api.v1.tenant.provision_tenant", new_callable=AsyncMock)
def test_provision_happy_path(mock_provision):
    mock_session = _mock_db_session()
    mock_tenant = MagicMock()
    mock_tenant.tenant_id = "t-001"
    mock_tenant.slug = "test-bank"
    mock_tenant.status = "active"
    mock_provision.return_value = mock_tenant

    app.dependency_overrides[get_current_user] = lambda: _mock_user("super_admin")
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.post("/api/v1/tenant/provision", json={
            "slug": "test-bank",
            "display_name": "Test Bank",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "test-bank"
        assert data["status"] == "active"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_async_db, None)


def test_get_tenant_not_found():
    mock_session = _mock_db_session(existing_tenant=None)
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.get("/api/v1/tenant/nonexistent")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_async_db, None)


def test_get_tenant_found():
    tenant = MagicMock()
    tenant.tenant_id = "t-001"
    tenant.slug = "test-bank"
    tenant.display_name = "Test Bank"
    tenant.tier = "bank"
    tenant.status = "active"
    tenant.data_region = "ap-south-1"
    tenant.created_at = MagicMock()
    tenant.created_at.isoformat.return_value = "2025-01-01T00:00:00Z"

    mock_session = _mock_db_session(existing_tenant=tenant)
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.dependency_overrides[get_async_db] = lambda: mock_session
    try:
        resp = client.get("/api/v1/tenant/t-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "test-bank"
        assert data["tier"] == "bank"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_async_db, None)
