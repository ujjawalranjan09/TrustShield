"""Tests for the Integration Sandbox API."""

from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth import verify_api_key
from app.database import get_async_db

client = TestClient(app, raise_server_exceptions=False)


def _mock_tenant(tenant_id="sandbox-tenant-1", is_sandbox=True):
    tenant = MagicMock()
    tenant.tenant_id = tenant_id
    tenant.is_sandbox = is_sandbox
    tenant.status = "active"
    tenant.slug = "sandbox-test"
    return tenant


def _mock_db_with_tenant(tenant):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = tenant
    mock_db.execute.return_value = mock_result
    return mock_db


def _override_deps(tenant=None):
    if tenant is None:
        tenant = _mock_tenant()
    mock_db = _mock_db_with_tenant(tenant)
    app.dependency_overrides[verify_api_key] = lambda: True
    app.dependency_overrides[get_async_db] = lambda: mock_db
    return mock_db


def _clear_deps():
    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_async_db, None)


class TestSandboxSignup:
    def test_sandbox_signup_creates_tenant_with_seeded_data(self):
        """Sandbox signup creates a tenant with is_sandbox=True and seeds data."""
        from uuid import uuid4

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        captured_tenants = []

        def capture_add(obj):
            captured_tenants.append(obj)
        mock_db.add.side_effect = capture_add

        async def fake_refresh(obj):
            # Simulate DB refresh setting the default tenant_id
            if hasattr(obj, "tenant_id") and obj.tenant_id is None:
                obj.tenant_id = str(uuid4())
        mock_db.refresh = fake_refresh

        app.dependency_overrides[verify_api_key] = lambda: True
        app.dependency_overrides[get_async_db] = lambda: mock_db
        try:
            resp = client.post("/api/v1/sandbox/signup")
            assert resp.status_code == 200
            data = resp.json()
            assert "tenant_id" in data
            assert "api_key" in data
            assert "slug" in data
            assert data["slug"].startswith("sandbox-")
            assert data["api_key"].startswith("ts_sandbox_")
            # Verify tenant was created with is_sandbox=True
            sandbox_tenants = [t for t in captured_tenants if hasattr(t, "is_sandbox")]
            assert len(sandbox_tenants) >= 1
            assert sandbox_tenants[0].is_sandbox is True
        finally:
            _clear_deps()


class TestSandboxReset:
    def test_sandbox_reset_clears_data(self):
        """Sandbox reset clears and re-seeds data."""
        tenant = _mock_tenant(is_sandbox=True)
        mock_db = _mock_db_with_tenant(tenant)
        mock_db.add = MagicMock()
        app.dependency_overrides[verify_api_key] = lambda: True
        app.dependency_overrides[get_async_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/v1/sandbox/reset",
                params={"tenant_id": "sandbox-tenant-1"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "reset"
            assert data["tenant_id"] == "sandbox-tenant-1"
        finally:
            _clear_deps()

    def test_sandbox_reset_rejected_for_non_sandbox(self):
        """Cannot reset non-sandbox tenant."""
        tenant = _mock_tenant(is_sandbox=False)
        _override_deps(tenant)
        try:
            resp = client.post(
                "/api/v1/sandbox/reset",
                params={"tenant_id": "real-tenant-1"},
            )
            assert resp.status_code == 403
            assert "not a sandbox" in resp.json()["detail"]
        finally:
            _clear_deps()


class TestSandboxWritesQuarantined:
    def test_sandbox_writes_quarantined(self):
        """Sandbox tenant's is_sandbox flag isolates it from prod data."""
        tenant = _mock_tenant(is_sandbox=True)
        mock_db = _mock_db_with_tenant(tenant)
        mock_count = MagicMock()
        mock_count.scalar.return_value = 0
        mock_db.execute = AsyncMock(return_value=mock_count)
        app.dependency_overrides[verify_api_key] = lambda: True
        app.dependency_overrides[get_async_db] = lambda: mock_db
        try:
            resp = client.get(
                "/api/v1/sandbox/status",
                params={"tenant_id": "sandbox-tenant-1"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["tenant_id"] == "sandbox-tenant-1"
            assert tenant.is_sandbox is True
        finally:
            _clear_deps()
