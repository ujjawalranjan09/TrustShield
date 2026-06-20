"""Unit tests for bank freeze/hold channel (D4.3)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    return db


def _mock_bank(freeze_webhook_url="https://bank.example.com/freeze"):
    bank = MagicMock()
    bank.bank_id = "BANK-001"
    bank.freeze_webhook_url = freeze_webhook_url
    return bank


def _mock_response(status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    return resp


@pytest.mark.asyncio
@patch("app.services.intervention.bank_channel.httpx.AsyncClient")
async def test_freeze_request_with_webhook_url(mock_client_cls, mock_db):
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=_mock_response())
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = _mock_bank()

    from app.services.intervention.bank_channel import send_freeze_request

    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await send_freeze_request(
        case_id="CASE-100",
        victim_entity="+919876543210",
        risk=0.92,
        recommended_action="hold",
        ttl_seconds=3600,
        db=mock_db,
    )

    assert result["status"] == "sent"
    assert result["bank_id"] == "BANK-001"
    mock_instance.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_freeze_request_without_webhook_returns_dashboard_only(mock_db):
    mock_bank = _mock_bank(freeze_webhook_url=None)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_bank
    mock_db.execute = AsyncMock(return_value=mock_result)

    from app.services.intervention.bank_channel import send_freeze_request

    result = await send_freeze_request(
        case_id="CASE-200",
        victim_entity="+919876543210",
        risk=0.85,
        recommended_action="hold",
        ttl_seconds=3600,
        db=mock_db,
    )

    assert result["status"] == "dashboard_only"
    assert result["bank_id"] == "BANK-001"
    assert "no webhook configured" in result["reason"]


@pytest.mark.asyncio
@patch("app.services.intervention.bank_channel.httpx.AsyncClient")
async def test_freeze_request_creates_intervention_log(mock_client_cls, mock_db):
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=_mock_response())
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = _mock_bank()
    mock_db.execute = AsyncMock(return_value=mock_result)

    from app.services.intervention.bank_channel import send_freeze_request

    await send_freeze_request(
        case_id="CASE-300",
        victim_entity="+919876543210",
        risk=0.92,
        recommended_action="hold",
        ttl_seconds=3600,
        db=mock_db,
    )

    mock_db.add.assert_called_once()
    log_entry = mock_db.add.call_args[0][0]
    assert log_entry.intervention_type == "bank_freeze_request"
    assert log_entry.status == "sent"


@pytest.mark.asyncio
async def test_missing_bank_returns_error(mock_db):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    from app.services.intervention.bank_channel import send_freeze_request

    result = await send_freeze_request(
        case_id="CASE-400",
        victim_entity="+919876543210",
        risk=0.92,
        recommended_action="hold",
        ttl_seconds=3600,
        db=mock_db,
    )

    assert result["status"] == "error"
    assert result["reason"] == "no_bank_found"
