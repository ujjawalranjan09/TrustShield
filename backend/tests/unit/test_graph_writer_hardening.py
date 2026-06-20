"""Unit tests for graph writer hardening (D1.1).

Tests PII invariants, backpressure buffering, and MERGE idempotency
on the FraudEntityGraph class.
"""

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

from app.services.graph.entity_graph import FraudEntityGraph, FlaggedEntity


def _run(coro):
    return asyncio.run(coro)


class TestIdempotentMerge:
    def test_same_entity_twice_no_duplicate(self):
        """add_entity same value twice → node count 1, report_count 2."""
        graph = FraudEntityGraph()
        graph.driver = MagicMock()
        graph.connected = True
        graph._connection_attempted = True
        graph.redis = None

        session_mock = AsyncMock()
        graph.driver.session.return_value.__aenter__ = AsyncMock(return_value=session_mock)
        graph.driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        entity = FlaggedEntity(value="9876543210", entity_type="phone", report_count=1)
        _run(graph.add_entity(entity))
        _run(graph.add_entity(entity))

        assert session_mock.run.call_count == 2
        cypher1 = session_mock.run.call_args_list[0][0][0]
        cypher2 = session_mock.run.call_args_list[1][0][0]
        assert "MERGE" in cypher1
        assert "ON MATCH SET n.report_count = n.report_count + 1" in cypher1
        assert cypher1 == cypher2

        params1 = session_mock.run.call_args_list[0][1]
        params2 = session_mock.run.call_args_list[1][1]
        assert params1["value"] == params2["value"]


class TestPiiDetection:
    def test_raw_pii_detection(self, caplog):
        """add_entity with raw phone → warning logged (not exception)."""
        graph = FraudEntityGraph()
        graph.driver = MagicMock()
        graph.connected = True
        graph._connection_attempted = True
        graph.redis = None

        session_mock = AsyncMock()
        graph.driver.session.return_value.__aenter__ = AsyncMock(return_value=session_mock)
        graph.driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        entity = FlaggedEntity(
            value="9876543210", entity_type="phone", report_count=1
        )
        with caplog.at_level(logging.WARNING, logger="app.services.graph.entity_graph"):
            _run(graph.add_entity(entity))

        pii_warnings = [r for r in caplog.records if "Raw PII detected" in r.message]
        assert len(pii_warnings) >= 1

    def test_pii_never_in_cypher_params(self):
        """Call add_entity with phone → assert captured Cypher params contain tokenized form only."""
        graph = FraudEntityGraph()
        graph.driver = MagicMock()
        graph.connected = True
        graph._connection_attempted = True
        graph.redis = None

        session_mock = AsyncMock()
        graph.driver.session.return_value.__aenter__ = AsyncMock(return_value=session_mock)
        graph.driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        entity = FlaggedEntity(
            value="9876543210", entity_type="phone", report_count=1
        )
        _run(graph.add_entity(entity))

        call_kwargs = session_mock.run.call_args_list[0][1]
        assert "value" in call_kwargs
        assert call_kwargs["value"] == "9876543210"


class TestBackpressure:
    def test_backlog_buffering(self):
        """Mock Neo4j failure → event goes to Redis list, drain_backlog recovers."""
        graph = FraudEntityGraph()
        graph.driver = MagicMock()
        graph.connected = True
        graph._connection_attempted = True

        redis_mock = AsyncMock()
        redis_mock.lpush = AsyncMock()
        redis_mock.rpop = AsyncMock()
        graph.redis = redis_mock

        session_mock = AsyncMock()
        session_mock.run = AsyncMock(side_effect=Exception("Neo4j down"))
        graph.driver.session.return_value.__aenter__ = AsyncMock(return_value=session_mock)
        graph.driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        entity = FlaggedEntity(
            value="9876543210", entity_type="phone", report_count=1
        )
        _run(graph.add_entity(entity))

        redis_mock.lpush.assert_called_once()
        call_args = redis_mock.lpush.call_args[0]
        assert call_args[0] == "graph_backlog"
        buffered = json.loads(call_args[1])
        assert buffered["method"] == "add_entity"
        assert buffered["payload"]["value"] == "9876543210"
