"""Unit tests for the intervention evaluator (D4.1)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest



@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


def _make_event(risk=0.95, consented=True, session_id="sess-100", entity_value="+919876543210"):
    return {
        "entity_value": entity_value,
        "entity_type": "PHONE",
        "scam_type": "vishing",
        "risk": risk,
        "source": "analyze",
        "session_id": session_id,
        "consented": consented,
    }


@pytest.mark.asyncio
async def test_high_risk_with_consent_enqueues_intervention(mock_db):
    with patch("app.services.intervention.action_engine.settings") as mock_settings:
        mock_settings.proactive_intervention_enabled = True
        mock_settings.intervention_risk_threshold = 0.8
        from app.services.intervention.action_engine import evaluate_intervention

        result = await evaluate_intervention(_make_event(), mock_db)

    assert result["intervention_enqueued"] is True
    assert result["reason"] == "high_risk_with_consent"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_high_risk_without_consent_skips_intervention(mock_db):
    with patch("app.services.intervention.action_engine.settings") as mock_settings:
        mock_settings.proactive_intervention_enabled = True
        mock_settings.intervention_risk_threshold = 0.8
        from app.services.intervention.action_engine import evaluate_intervention

        result = await evaluate_intervention(_make_event(consented=False), mock_db)

    assert result["intervention_enqueued"] is False
    assert result["reason"] == "no_dpdp_consent"
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_below_threshold_no_intervention(mock_db):
    with patch("app.services.intervention.action_engine.settings") as mock_settings:
        mock_settings.proactive_intervention_enabled = True
        mock_settings.intervention_risk_threshold = 0.8
        from app.services.intervention.action_engine import evaluate_intervention

        result = await evaluate_intervention(_make_event(risk=0.5), mock_db)

    assert result["intervention_enqueued"] is False
    assert result["reason"] == "risk_below_threshold"
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_globally_no_intervention(mock_db):
    with patch("app.services.intervention.action_engine.settings") as mock_settings:
        mock_settings.proactive_intervention_enabled = False
        mock_settings.intervention_risk_threshold = 0.8
        from app.services.intervention.action_engine import evaluate_intervention

        result = await evaluate_intervention(_make_event(), mock_db)

    assert result["intervention_enqueued"] is False
    assert result["reason"] == "proactive_intervention_disabled"
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_ring_membership_triggers_intervention(mock_db):
    with patch("app.services.intervention.action_engine.settings") as mock_settings:
        mock_settings.proactive_intervention_enabled = True
        mock_settings.intervention_risk_threshold = 0.8
        from app.services.intervention.action_engine import evaluate_intervention

        event = _make_event(risk=0.95, consented=True)
        event["in_fraud_ring"] = True
        result = await evaluate_intervention(event, mock_db)

    assert result["intervention_enqueued"] is True
    assert result["reason"] == "high_risk_with_consent"
    mock_db.add.assert_called_once()
