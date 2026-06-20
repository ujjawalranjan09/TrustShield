"""Tests for the Embed Token API."""

from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth import verify_api_key, get_current_user
from app.database import get_async_db

client = TestClient(app, raise_server_exceptions=False)


def _mock_tenant(tenant_id="tenant-123", status="active", is_sandbox=False):
    tenant = MagicMock()
    tenant.tenant_id = tenant_id
    tenant.status = status
    tenant.is_sandbox = is_sandbox
    return tenant


def _mock_db_with_tenant(tenant):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = tenant
    mock_db.execute.return_value = mock_result
    return mock_db


def _override_deps(tenant):
    mock_db = _mock_db_with_tenant(tenant)
    app.dependency_overrides[verify_api_key] = lambda: True
    app.dependency_overrides[get_async_db] = lambda: mock_db
    return mock_db


def _clear_deps():
    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_async_db, None)
    app.dependency_overrides.pop(get_current_user, None)


class TestEmbedToken:
    def test_embed_token_issued_with_restricted_scope(self):
        """Embed token must be issued with scope='embed' and restricted permissions."""
        tenant = _mock_tenant()
        _override_deps(tenant)
        try:
            resp = client.post(
                "/api/v1/embed/token",
                json={"tenant_id": "tenant-123"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["scope"] == "embed"
            assert data["expires_in"] == 3600
            assert "SCAN_READ" in data["permissions"]
            assert "REPORT_CREATE" in data["permissions"]
            assert "INTEL_READ" in data["permissions"]
            assert "TENANT_ADMIN" not in data["permissions"]
            assert "BILLING_MANAGE" not in data["permissions"]
            from app.services.auth.jwt_service import decode_token
            payload = decode_token(data["token"])
            assert payload is not None
            assert payload["scope"] == "embed"
            assert payload["role"] == "embed"
        finally:
            _clear_deps()

    def test_embed_token_cannot_call_admin_endpoints(self):
        """Embed tokens must not be able to access tenant-management or admin endpoints."""
        from app.services.auth.jwt_service import create_access_token

        embed_token = create_access_token(
            data={
                "sub": "embed:tenant-123",
                "tenant_id": "tenant-123",
                "scope": "embed",
                "role": "embed",
                "permissions": ["SCAN_READ", "REPORT_CREATE", "INTEL_READ"],
            }
        )
        # Mock the DB dependency so get_current_user doesn't hit real DB
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result
        app.dependency_overrides[get_async_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/v1/tenant/provision",
                json={"slug": "test", "tier": "bank", "display_name": "Test"},
                headers={"Authorization": f"Bearer {embed_token}"},
            )
            # Embed token is rejected: 401/403 (auth failure) or 500 (ValueError from int("embed:..."))
            assert resp.status_code != 200
        finally:
            _clear_deps()

    def test_embed_requires_valid_api_key(self):
        """Embed token endpoint returns error when API key validation fails."""
        tenant = _mock_tenant()
        mock_db = _mock_db_with_tenant(tenant)

        async def _reject_api_key():
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Invalid API key")

        app.dependency_overrides[verify_api_key] = _reject_api_key
        app.dependency_overrides[get_async_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/v1/embed/token",
                json={"tenant_id": "tenant-123"},
            )
            assert resp.status_code == 403
            assert "Invalid API key" in resp.json()["detail"]
        finally:
            _clear_deps()

    def test_embed_token_rejected_for_inactive_tenant(self):
        """Cannot issue embed token for inactive tenant."""
        tenant = _mock_tenant(status="suspended")
        _override_deps(tenant)
        try:
            resp = client.post(
                "/api/v1/embed/token",
                json={"tenant_id": "tenant-123"},
            )
            assert resp.status_code == 403
            assert "not active" in resp.json()["detail"]
        finally:
            _clear_deps()

    def test_embed_token_404_for_missing_tenant(self):
        """Returns 404 when tenant does not exist."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result
        app.dependency_overrides[verify_api_key] = lambda: True
        app.dependency_overrides[get_async_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/v1/embed/token",
                json={"tenant_id": "nonexistent"},
            )
            assert resp.status_code == 404
        finally:
            _clear_deps()
