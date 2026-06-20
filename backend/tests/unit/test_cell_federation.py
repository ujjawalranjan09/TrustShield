"""Unit tests for cross-cell reputation federation."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.intel.cell_federation import (
    _aggregate_scores,
    _parse_cell_urls,
    _recency_weight,
    federation_health_check,
    federated_reputation_lookup,
)


def test_parse_cell_urls_empty():
    with patch("app.services.intel.cell_federation.settings") as mock_settings:
        mock_settings.cell_urls = ""
        assert _parse_cell_urls() == {}


def test_parse_cell_urls_invalid_json():
    with patch("app.services.intel.cell_federation.settings") as mock_settings:
        mock_settings.cell_urls = "not-json"
        assert _parse_cell_urls() == {}


def test_parse_cell_urls_valid():
    with patch("app.services.intel.cell_federation.settings") as mock_settings:
        mock_settings.cell_urls = '{"ap-south-1": "https://ap.trustshield.io"}'
        result = _parse_cell_urls()
        assert result == {"ap-south-1": "https://ap.trustshield.io"}


def test_recency_weight_recent():
    now = datetime.now(timezone.utc)
    assert _recency_weight(now) == 1.0


def test_recency_weight_old():
    from datetime import timedelta
    old = datetime.now(timezone.utc) - timedelta(days=200)
    assert _recency_weight(old) == 0.1


def test_recency_weight_none():
    assert _recency_weight(None) == 0.1


def test_aggregate_scores_local_only():
    result = _aggregate_scores(50, datetime.now(timezone.utc), [])
    assert result["score"] == 50
    assert result["peer_count"] == 0
    assert result["sources"] == ["local"]


def test_aggregate_scores_with_peers():
    now = datetime.now(timezone.utc)
    peers = [
        {"score": 80, "last_seen": now, "source": "peer1"},
        {"score": 40, "last_seen": now, "source": "peer2"},
    ]
    result = _aggregate_scores(50, now, peers)
    assert result["peer_count"] == 2
    assert 40 <= result["score"] <= 80


def test_aggregate_scores_clamped():
    result = _aggregate_scores(200, None, [])
    assert result["score"] == 100


def test_aggregate_scores_clamped_low():
    result = _aggregate_scores(-10, None, [])
    assert result["score"] == 0


@pytest.mark.asyncio
async def test_local_reputation_used_when_no_peers():
    """When no peer cells are configured, federation returns local-only."""
    local_result = {
        "entity": "9876543210",
        "score": 42,
        "reputation_tier": "watch",
        "last_reported_at": None,
    }

    with patch("app.services.intel.cell_federation.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_urls = ""

        with patch(
            "app.services.intel.reputation_service.compute_reputation",
            new_callable=AsyncMock,
            return_value=local_result,
        ):
            db = MagicMock()
            result = await federated_reputation_lookup("9876543210", "phone", db)

    assert result["score"] == 42
    assert result["federation"]["peer_count"] == 0
    assert "local" in result["federation"]["sources"]


@pytest.mark.asyncio
async def test_federation_aggregates_scores():
    """Federation aggregates local + peer scores."""
    local_result = {
        "entity": "9876543210",
        "score": 30,
        "reputation_tier": "watch",
        "last_reported_at": datetime.now(timezone.utc).isoformat(),
    }
    peer_result = {
        "score": 70,
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "source": "https://us-east-1.trustshield.io",
    }

    with patch("app.services.intel.cell_federation.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_urls = '{"us-east-1": "https://us-east-1.trustshield.io"}'

        with patch(
            "app.services.intel.reputation_service.compute_reputation",
            new_callable=AsyncMock,
            return_value=local_result,
        ):
            with patch(
                "app.services.intel.cell_federation._query_peer_cell",
                new_callable=AsyncMock,
                return_value=peer_result,
            ):
                db = MagicMock()
                result = await federated_reputation_lookup("9876543210", "phone", db)

    assert result["federation"]["peer_count"] == 1
    assert 30 <= result["score"] <= 70


@pytest.mark.asyncio
async def test_federation_down_degrades_gracefully():
    """When peer cell is unreachable, local reputation is returned."""
    local_result = {
        "entity": "9876543210",
        "score": 25,
        "reputation_tier": "watch",
        "last_reported_at": None,
    }

    with patch("app.services.intel.cell_federation.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_urls = '{"us-east-1": "https://us-east-1.trustshield.io"}'

        with patch(
            "app.services.intel.reputation_service.compute_reputation",
            new_callable=AsyncMock,
            return_value=local_result,
        ):
            with patch(
                "app.services.intel.cell_federation._query_peer_cell",
                new_callable=AsyncMock,
                side_effect=Exception("Connection refused"),
            ):
                db = MagicMock()
                result = await federated_reputation_lookup("9876543210", "phone", db)

    assert result["score"] == 25
    assert result["federation"]["peer_count"] == 0


@pytest.mark.asyncio
async def test_entity_tokenized_before_federation():
    """Entity value must be tokenized before sending to peer cells."""
    local_result = {
        "entity": "9876543210",
        "score": 10,
        "reputation_tier": "clean",
        "last_reported_at": None,
    }

    with patch("app.services.intel.cell_federation.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_urls = '{"us-east-1": "https://us-east-1.trustshield.io"}'

        with patch(
            "app.services.intel.reputation_service.compute_reputation",
            new_callable=AsyncMock,
            return_value=local_result,
        ):
            with patch(
                "app.services.intel.cell_federation._query_peer_cell",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_query:
                db = MagicMock()
                await federated_reputation_lookup("9876543210", "phone", db)

                # Verify tokenized entity was passed to peer
                call_args = mock_query.call_args
                tokenized = call_args[0][1]  # second positional arg
                assert tokenized.startswith("tkn_phone_")
                assert "9876543210" not in tokenized


@pytest.mark.asyncio
async def test_federation_health_check_no_peers():
    """Health check returns healthy when no peers are configured."""
    with patch("app.services.intel.cell_federation.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_urls = ""

        result = await federation_health_check()

    assert result["all_healthy"] is True
    assert result["peers"] == {}


@pytest.mark.asyncio
async def test_federation_health_check_with_peers():
    """Health check reports status of each peer cell."""
    with patch("app.services.intel.cell_federation.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_urls = '{"us-east-1": "https://us-east-1.trustshield.io"}'

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("app.services.intel.cell_federation.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await federation_health_check()

    assert result["local_region"] == "ap-south-1"
    assert "us-east-1" in result["peers"]
    assert result["all_healthy"] is True
