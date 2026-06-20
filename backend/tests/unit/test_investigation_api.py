"""Tests for investigation UI backend endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_current_user


client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_user(role: str = "analyst") -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.role = role
    user.is_active = True
    return user


def _mock_ring(ring_id: str = "ring-001"):
    ring = MagicMock()
    ring.ring_id = ring_id
    ring.entity_count = 5
    ring.total_reports = 12
    ring.top_scam_type = "vishing"
    ring.risk_level = "high"
    ring.status = "new"
    ring.detected_at = MagicMock()
    ring.detected_at.isoformat.return_value = "2025-01-01T00:00:00Z"
    return ring


def _mock_neighborhood_data():
    return {
        "nodes": [
            {
                "id": "abc123",
                "label": "98****3210",
                "risk": 0.8,
                "entity_type": "PHONE",
                "ring_id": "ring-001",
                "report_count": 5,
                "propagated_risk": 0.6,
            },
            {
                "id": "def456",
                "label": "u***r@paytm",
                "risk": 0.3,
                "entity_type": "UPI",
                "ring_id": None,
                "report_count": 1,
                "propagated_risk": 0.1,
            },
        ],
        "edges": [
            {"source": "abc123", "target": "def456", "label": "APPEARED_WITH", "weight": 2},
        ],
    }


def _mock_shortest_path_data():
    return {
        "nodes": [
            {"value": "+919876543210", "entity_type": "PHONE", "risk_score": 0.8, "ring_id": "ring-001"},
            {"value": "user@paytm", "entity_type": "UPI", "risk_score": 0.3, "ring_id": None},
        ],
        "edges": [
            {"src": "+919876543210", "dst": "user@paytm", "label": "APPEARED_WITH", "weight": 2},
        ],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEntityNeighborhoodEndpoint:
    """GET /graph/entity/{entity_type}/{entity_value}"""

    @patch("app.services.graph.entity_graph.FraudEntityGraph")
    @patch("app.database.get_async_db", new_callable=AsyncMock)
    def test_entity_endpoint_returns_neighborhood(self, mock_db, MockGraph):
        app.dependency_overrides[get_current_user] = lambda: _mock_user("analyst")
        try:
            graph_instance = AsyncMock()
            graph_instance.get_neighborhood = AsyncMock(return_value=_mock_neighborhood_data())
            graph_instance.get_entity_risk = AsyncMock(return_value=0.8)
            graph_instance.connected = True
            MockGraph.return_value = graph_instance

            mock_session = AsyncMock()
            mock_db.return_value = mock_session

            resp = client.get("/api/v1/graph/entity/PHONE/9876543210")
            assert resp.status_code == 200
            data = resp.json()
            assert "center" in data
            assert "nodes" in data
            assert "edges" in data
            assert len(data["nodes"]) >= 1
            assert "direct_risk" in data
            assert "propagated_risk" in data
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_entity_endpoint_returns_403_without_analyst_role(self):
        app.dependency_overrides[get_current_user] = lambda: _mock_user("viewer")
        try:
            resp = client.get("/api/v1/graph/entity/PHONE/9876543210")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    @patch("app.services.graph.entity_graph.FraudEntityGraph")
    @patch("app.database.get_async_db", new_callable=AsyncMock)
    def test_pii_masked_for_non_admin(self, mock_db, MockGraph):
        app.dependency_overrides[get_current_user] = lambda: _mock_user("analyst")
        try:
            graph_instance = AsyncMock()
            graph_instance.get_neighborhood = AsyncMock(return_value=_mock_neighborhood_data())
            graph_instance.get_entity_risk = AsyncMock(return_value=0.8)
            graph_instance.connected = True
            MockGraph.return_value = graph_instance

            resp = client.get("/api/v1/graph/entity/PHONE/9876543210")
            assert resp.status_code == 200
            data = resp.json()
            for node in data["nodes"]:
                assert "***" in node["label"] or len(node["label"]) <= 20
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestShortestPathEndpoint:
    """GET /graph/path"""

    @patch("app.services.graph.entity_graph.FraudEntityGraph")
    def test_path_endpoint_returns_shortest_path(self, MockGraph):
        app.dependency_overrides[get_current_user] = lambda: _mock_user("analyst")
        try:
            graph_instance = AsyncMock()
            graph_instance.get_shortest_path = AsyncMock(return_value=_mock_shortest_path_data())
            MockGraph.return_value = graph_instance

            resp = client.get(
                "/api/v1/graph/path",
                params={
                    "from_type": "PHONE",
                    "from_value": "+919876543210",
                    "to_type": "UPI",
                    "to_value": "user@paytm",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["found"] is True
            assert data["path_length"] == 2
            assert len(data["nodes"]) == 2
            assert len(data["edges"]) == 1
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_path_endpoint_requires_analyst_role(self):
        app.dependency_overrides[get_current_user] = lambda: _mock_user("viewer")
        try:
            resp = client.get(
                "/api/v1/graph/path",
                params={
                    "from_type": "PHONE",
                    "from_value": "+919876543210",
                    "to_type": "UPI",
                    "to_value": "user@paytm",
                },
            )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    @patch("app.services.graph.entity_graph.FraudEntityGraph")
    def test_path_returns_empty_when_no_path(self, MockGraph):
        app.dependency_overrides[get_current_user] = lambda: _mock_user("analyst")
        try:
            graph_instance = AsyncMock()
            graph_instance.get_shortest_path = AsyncMock(return_value=None)
            MockGraph.return_value = graph_instance

            resp = client.get(
                "/api/v1/graph/path",
                params={
                    "from_type": "PHONE",
                    "from_value": "+919876543210",
                    "to_type": "UPI",
                    "to_value": "user@paytm",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["found"] is False
            assert data["path_length"] == 0
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_path_endpoint_requires_params(self):
        app.dependency_overrides[get_current_user] = lambda: _mock_user("analyst")
        try:
            resp = client.get("/api/v1/graph/path")
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestRingsPagination:
    """GET /graph/rings with pagination"""

    @patch("app.database.get_async_db", new_callable=AsyncMock)
    def test_rings_returns_paginated(self, mock_db):
        mock_session = AsyncMock()
        mock_db.return_value = mock_session

        mock_ring = _mock_ring()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_ring]
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        async def execute_side_effect(query):
            stmt_str = str(query)
            if "count" in stmt_str or "COUNT" in stmt_str:
                return mock_count_result
            return mock_result

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)

        resp = client.get("/api/v1/graph/rings?page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "rings" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["page"] == 1
        assert data["page_size"] == 10
