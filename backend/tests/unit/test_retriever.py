"""Unit tests for the explainability retriever."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.explain.retriever import retrieve


def _make_focal(**overrides):
    focal = MagicMock()
    focal.session_id = overrides.get("session_id", "s1")
    focal.risk_score = overrides.get("risk_score", 85)
    focal.risk_level = overrides.get("risk_level", "HIGH")
    focal.action_taken = overrides.get("action_taken", "block")
    focal.entities_found = overrides.get("entities_found", 3)
    focal.scan_type = overrides.get("scan_type", "analyze")
    focal.entities = overrides.get("entities", None)
    focal.attributions = overrides.get("attributions", None)
    return focal


def _make_db_with_focal(focal, similar=None):
    db = AsyncMock()
    focal_result = MagicMock()
    focal_result.scalars.return_value.first.return_value = focal
    if similar is None:
        similar = []
    with patch(
        "app.services.explain.retriever.find_similar_sessions",
        new_callable=AsyncMock,
        return_value=similar,
    ) as mock_find:
        db._focal_result = focal_result
        db._mock_find = mock_find
        return db, mock_find


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retriever_returns_focal_and_neighbors():
    focal = _make_focal()
    similar = [
        {"session_id": "s2", "similarity": 0.92},
        {"session_id": "s3", "similarity": 0.87},
    ]
    db = AsyncMock()
    focal_result = MagicMock()
    focal_result.scalars.return_value.first.return_value = focal
    db.execute.return_value = focal_result

    with patch(
        "app.services.explain.retriever.find_similar_sessions",
        new_callable=AsyncMock,
        return_value=similar,
    ):
        data = await retrieve("Why flagged?", "s1", db)

    types = [c["type"] for c in data["context"]]
    assert types[0] == "focal_session"
    assert types.count("similar_session") == 2
    assert len(data["sources"]) == 1 + 2


@pytest.mark.asyncio
async def test_nonexistent_session_returns_empty_context():
    db = AsyncMock()
    focal_result = MagicMock()
    focal_result.scalars.return_value.first.return_value = None
    db.execute.return_value = focal_result

    data = await retrieve("Why flagged?", "nonexistent", db)

    assert data["context"] == []
    assert data["sources"] == []


@pytest.mark.asyncio
async def test_retriever_includes_attribution_data():
    focal = _make_focal(
        entities=[{"type": "PHONE", "value": "+919876543210"}],
        attributions={"risk_factors": ["otp_request", "urgency"]},
    )
    similar = [{"session_id": "s2", "similarity": 0.80}]
    db = AsyncMock()
    focal_result = MagicMock()
    focal_result.scalars.return_value.first.return_value = focal
    db.execute.return_value = focal_result

    with patch(
        "app.services.explain.retriever.find_similar_sessions",
        new_callable=AsyncMock,
        return_value=similar,
    ):
        data = await retrieve("Explain risk", "s1", db)

    types = [c["type"] for c in data["context"]]
    assert "entity_matches" in types
    assert "attributions" in types

    entity_ctx = next(c for c in data["context"] if c["type"] == "entity_matches")
    assert entity_ctx["entities"][0]["type"] == "PHONE"

    attr_ctx = next(c for c in data["context"] if c["type"] == "attributions")
    assert "otp_request" in attr_ctx["data"]["risk_factors"]
