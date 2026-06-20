"""Unit tests for graph lifecycle: ingest, ring detection, risk propagation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.graph.entity_graph import FlaggedEntity, FraudEntityGraph


def _run(coro):
    return asyncio.run(coro)


class _MockGraph:
    def __init__(self):
        self.graph = FraudEntityGraph()
        self.graph.driver = MagicMock()
        self.graph.driver.close = AsyncMock()
        self.graph.connected = True
        self.graph._connection_attempted = True
        self.graph.redis = None
        self.session_mock = AsyncMock()
        self.graph.driver.session.return_value.__aenter__ = AsyncMock(
            return_value=self.session_mock
        )
        self.graph.driver.session.return_value.__aexit__ = AsyncMock(return_value=False)


class TestEntityIngestedToGraph:
    def test_entity_ingested_to_graph(self):
        mg = _MockGraph()
        entity = FlaggedEntity(value="9876543210", entity_type="phone", report_count=1)
        _run(mg.graph.add_entity(entity))

        assert mg.session_mock.run.call_count == 1
        cypher = mg.session_mock.run.call_args_list[0][0][0]
        assert "MERGE" in cypher
        params = mg.session_mock.run.call_args_list[0][1]
        assert params["value"] == "9876543210"
        assert params["type"] == "phone"
        assert params["report_count"] == 1


class TestRingDetectedAndPersisted:
    def test_ring_detected_and_persisted(self):
        mg = _MockGraph()
        ring_entities = [
            {"value": f"entity-{i}", "entity_type": "phone", "report_count": 10, "pagerank_score": 0.5}
            for i in range(6)
        ]
        edges = [(f"entity-{i}", f"entity-{i+1}") for i in range(5)]

        mg.session_mock.run = AsyncMock()
        mg.graph.get_all_entities = AsyncMock(return_value=ring_entities)
        mg.graph.update_ring_ids = AsyncMock()

        with patch(
            "app.services.graph.entity_graph.FraudEntityGraph", return_value=mg.graph
        ), patch(
            "app.services.graph.ring_detection._get_all_edges",
            new_callable=AsyncMock,
            return_value=edges,
        ), patch(
            "app.services.graph.ring_detection._persist_rings",
            new_callable=AsyncMock,
        ):
            from app.services.graph.ring_detection import _detect_rings

            result = _run(_detect_rings())

        assert result["status"] == "success"
        assert result["rings_found"] >= 0
        mg.graph.update_ring_ids.assert_called()


class TestRiskPropagationUpdatesScores:
    def test_risk_propagation_updates_scores(self):
        mg = _MockGraph()
        entities = [
            {"value": "bad-entity", "entity_type": "phone", "report_count": 10, "graph_risk_score": 0.9, "pagerank_score": 0.0},
            {"value": "linked-entity", "entity_type": "upi", "report_count": 2, "graph_risk_score": 0.3, "pagerank_score": 0.0},
        ]

        mg.session_mock.run = AsyncMock()
        mg.graph.update_entity_scores = AsyncMock()
        mg.graph.invalidate_all_risk_cache = AsyncMock()
        mg.graph.get_all_entities = AsyncMock(return_value=entities)

        with patch(
            "app.services.graph.entity_graph.FraudEntityGraph", return_value=mg.graph
        ), patch(
            "app.services.graph.risk_propagation._get_all_edges",
            new_callable=AsyncMock,
            return_value=[("bad-entity", "linked-entity")],
        ):
            from app.services.graph.risk_propagation import _propagate_risk_scores

            result = _run(_propagate_risk_scores())

        assert result["status"] == "success"
        assert result["nodes_updated"] == 2
        mg.graph.update_entity_scores.assert_called_once()
        updates_arg = mg.graph.update_entity_scores.call_args[0][0]
        assert len(updates_arg) == 2
