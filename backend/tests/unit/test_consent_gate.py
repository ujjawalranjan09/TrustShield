"""Unit tests for the DPDP consent gate in the intervention pipeline."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


def _make_event(consented=True, session_id="consent-sess-1", entity_value="+919876543210"):
    return {
        "entity_value": entity_value,
        "entity_type": "PHONE",
        "scam_type": "vishing",
        "risk": 0.95,
        "source": "analyze",
        "session_id": session_id,
        "consented": consented,
    }


@pytest.mark.asyncio
async def test_consent_present_allows_intervention(mock_db):
    with patch("app.services.intervention.action_engine.settings") as mock_settings:
        mock_settings.proactive_intervention_enabled = True
        mock_settings.intervention_risk_threshold = 0.8
        from app.services.intervention.action_engine import evaluate_intervention

        result = await evaluate_intervention(_make_event(consented=True), mock_db)

    assert result["intervention_enqueued"] is True
    assert result["reason"] == "high_risk_with_consent"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_consent_absent_blocks_intervention(mock_db):
    with patch("app.services.intervention.action_engine.settings") as mock_settings:
        mock_settings.proactive_intervention_enabled = True
        mock_settings.intervention_risk_threshold = 0.8
        from app.services.intervention.action_engine import evaluate_intervention

        result = await evaluate_intervention(_make_event(consented=False), mock_db)

    assert result["intervention_enqueued"] is False
    assert result["reason"] == "no_dpdp_consent"
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_consent_field_missing_blocks_intervention(mock_db):
    event = {
        "entity_value": "+919876543210",
        "entity_type": "PHONE",
        "scam_type": "vishing",
        "risk": 0.95,
        "source": "analyze",
        "session_id": "no-consent-sess",
    }
    with patch("app.services.intervention.action_engine.settings") as mock_settings:
        mock_settings.proactive_intervention_enabled = True
        mock_settings.intervention_risk_threshold = 0.8
        from app.services.intervention.action_engine import evaluate_intervention

        result = await evaluate_intervention(event, mock_db)

    assert result["intervention_enqueued"] is False
    assert result["reason"] == "no_dpdp_consent"
    mock_db.add.assert_not_called()
