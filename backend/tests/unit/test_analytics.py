"""Tests for analytics dashboard endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app, raise_server_exceptions=False)


def _mock_db_session():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


@patch("app.database.get_async_db", new_callable=AsyncMock)
def test_dashboard_stats_returns_200(mock_db):
    mock_db.return_value = _mock_db_session()
    resp = client.get("/api/v1/analytics/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_scans_today" in data
    assert "flagged_sessions" in data
    assert "risk_distribution" in data
    assert "scam_type_breakdown" in data
    assert "contributing_factors" in data
    assert "temporal_trend" in data


@patch("app.database.get_async_db", new_callable=AsyncMock)
def test_dashboard_stats_risk_distribution_shape(mock_db):
    mock_db.return_value = _mock_db_session()
    resp = client.get("/api/v1/analytics/dashboard")
    data = resp.json()
    rd = data["risk_distribution"]
    assert "low" in rd
    assert "medium" in rd
    assert "high" in rd
    assert "critical" in rd
    assert "total" in rd
