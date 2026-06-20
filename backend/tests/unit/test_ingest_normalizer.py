"""Unit tests for ingest normalizer."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.analyze import ScamType
from app.schemas.entity import EntityType
from app.services.intel.ingest_normalizer import (
    IntelEvent,
    _emit_to_graph,
    _emit_to_intervention,
    _emit_to_reputation,
    normalize_and_emit,
)


@pytest.fixture
def mock_db():
    return AsyncMock()


# ---------------------------------------------------------------------------
# normalize — analyze
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_analyze_event(mock_db):
    payload = {
        "session_metadata": {"session_id": "sess-001"},
        "entities": [{"entity_type": "PHONE", "value": "+919876543210"}],
        "scam_type": "vishing",
        "risk_score": 75,
    }

    with patch(
        "app.services.intel.ingest_normalizer._emit_to_graph", new_callable=AsyncMock
    ), patch(
        "app.services.intel.ingest_normalizer._emit_to_reputation", new_callable=AsyncMock
    ), patch(
        "app.services.intel.ingest_normalizer._emit_to_intervention", new_callable=AsyncMock
    ):
        event = await normalize_and_emit("analyze", payload, mock_db)

    assert event.session_id == "sess-001"
    assert event.entity_value == "+919876543210"
    assert event.entity_type == EntityType.PHONE
    assert event.scam_type == ScamType.VISHING
    assert event.risk == 75.0
    assert event.source == "analyze"


# ---------------------------------------------------------------------------
# normalize — report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_report_event(mock_db):
    payload = {
        "entity_value": "+91 98765 43210",
        "entity_type": "PHONE",
        "scam_type": "otp_harvesting",
        "report_count": 3,
        "report_id": "rpt-123",
    }

    with patch(
        "app.services.intel.ingest_normalizer._emit_to_graph", new_callable=AsyncMock
    ), patch(
        "app.services.intel.ingest_normalizer._emit_to_reputation", new_callable=AsyncMock
    ), patch(
        "app.services.intel.ingest_normalizer._emit_to_intervention", new_callable=AsyncMock
    ):
        event = await normalize_and_emit("report", payload, mock_db)

    assert event.entity_value == "+91 98765 43210"
    assert event.entity_type == EntityType.PHONE
    assert event.scam_type == ScamType.OTP_HARVESTING
    assert event.risk == 30.0
    assert event.source == "report"
    assert event.session_id == "report-rpt-123"


# ---------------------------------------------------------------------------
# normalize — voice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_voice_event(mock_db):
    payload = {
        "caller_id": "+911234567890",
        "entities": [{"entity_type": "ANYDESK", "value": "12345678"}],
        "scam_type": "remote_access",
        "risk_score": 85,
    }

    with patch(
        "app.services.intel.ingest_normalizer._emit_to_graph", new_callable=AsyncMock
    ), patch(
        "app.services.intel.ingest_normalizer._emit_to_reputation", new_callable=AsyncMock
    ), patch(
        "app.services.intel.ingest_normalizer._emit_to_intervention", new_callable=AsyncMock
    ):
        event = await normalize_and_emit("voice", payload, mock_db)

    assert event.entity_value == "12345678"
    assert event.entity_type == EntityType.ANYDESK
    assert event.scam_type == ScamType.REMOTE_ACCESS
    assert event.risk == 85.0
    assert event.source == "voice"


# ---------------------------------------------------------------------------
# normalize — image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_image_event(mock_db):
    payload = {
        "image_hash": "abc123",
        "qr_codes": [
            {"content": "https://evil.com", "content_type": "url", "is_suspicious": True}
        ],
        "risk_level": "high",
        "scam_type": "phishing",
    }

    with patch(
        "app.services.intel.ingest_normalizer._emit_to_graph", new_callable=AsyncMock
    ), patch(
        "app.services.intel.ingest_normalizer._emit_to_reputation", new_callable=AsyncMock
    ), patch(
        "app.services.intel.ingest_normalizer._emit_to_intervention", new_callable=AsyncMock
    ):
        event = await normalize_and_emit("image", payload, mock_db)

    assert event.entity_value == "https://evil.com"
    assert event.entity_type == EntityType.URL_SHORTLINK
    assert event.scam_type == ScamType.PHISHING
    assert event.risk == 70.0
    assert event.source == "image"


# ---------------------------------------------------------------------------
# Fanout — all three sinks called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fanout_invokes_all_sinks(mock_db):
    payload = {
        "session_metadata": {"session_id": "sess-002"},
        "entities": [{"entity_type": "UPI", "value": "fraud@upi"}],
        "scam_type": "phishing",
        "risk_score": 60,
    }

    with patch(
        "app.services.intel.ingest_normalizer._emit_to_graph", new_callable=AsyncMock
    ) as mock_graph, patch(
        "app.services.intel.ingest_normalizer._emit_to_reputation", new_callable=AsyncMock
    ) as mock_rep, patch(
        "app.services.intel.ingest_normalizer._emit_to_intervention", new_callable=AsyncMock
    ) as mock_int:
        await normalize_and_emit("analyze", payload, mock_db)
        await asyncio.sleep(0)

    assert mock_graph.call_count == 1
    assert mock_rep.call_count == 1
    assert mock_int.call_count == 1


# ---------------------------------------------------------------------------
# Sink isolation — one failure doesn't abort others
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sink_failure_doesnt_abort_others(mock_db):
    payload = {
        "session_metadata": {"session_id": "sess-003"},
        "entities": [{"entity_type": "PHONE", "value": "+910000000000"}],
        "scam_type": "unknown",
        "risk_score": 10,
    }

    async def _fail_graph(event):
        raise RuntimeError("graph exploded")

    with patch(
        "app.services.intel.ingest_normalizer._emit_to_graph", side_effect=_fail_graph
    ) as mock_graph, patch(
        "app.services.intel.ingest_normalizer._emit_to_reputation", new_callable=AsyncMock
    ) as mock_rep, patch(
        "app.services.intel.ingest_normalizer._emit_to_intervention", new_callable=AsyncMock
    ) as mock_int:
        event = await normalize_and_emit("analyze", payload, mock_db)
        await asyncio.sleep(0)

    assert event.entity_value == "+910000000000"
    assert mock_graph.call_count == 1
    assert mock_rep.call_count == 1
    assert mock_int.call_count == 1
