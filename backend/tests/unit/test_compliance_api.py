"""Tests for compliance endpoints."""

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


def test_compliance_health():
    resp = client.get("/api/v1/compliance/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "pipelines" in data


@patch("app.services.audit.verify_job.ack_audit_break", new_callable=AsyncMock)
def test_ack_break_requires_admin_role(mock_ack):
    app.dependency_overrides[get_current_user] = lambda: _mock_user("analyst")
    try:
        resp = client.post("/api/v1/audit/ack-break", json={"break_id": 1, "resolved_by": "admin"})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@patch("app.services.audit.verify_job.ack_audit_break", new_callable=AsyncMock)
def test_ack_break_happy_path(mock_ack):
    mock_ack.return_value = {"success": True}
    app.dependency_overrides[get_current_user] = lambda: _mock_user("admin")
    try:
        resp = client.post("/api/v1/audit/ack-break", json={"break_id": 1, "resolved_by": "admin"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["break_id"] == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)
