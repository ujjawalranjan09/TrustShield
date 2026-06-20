"""Unit tests for WhatsApp outbound warning sender (D4.2)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    return db


def _mock_response(status_code=200, text='{"messages":[{"id":"wamid.mock"}]}'):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


@pytest.mark.asyncio
@patch("app.services.intervention.whatsapp_sender.httpx.AsyncClient")
@patch("app.services.intervention.whatsapp_sender.settings")
async def test_send_warning_calls_whatsapp_api(mock_settings, mock_client_cls, mock_db):
    mock_settings.whatsapp_outbound_enabled = True
    mock_settings.whatsapp_phone_number_id = "12345"
    mock_settings.whatsapp_access_token = "tok_test"

    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=_mock_response())
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    from app.services.intervention.whatsapp_sender import send_whatsapp_warning

    result = await send_whatsapp_warning("+919876543210", "Scam alert", mock_db)

    assert result["sent"] is True
    assert result["status"] == "sent"
    mock_instance.post.assert_awaited_once()
    call_kwargs = mock_instance.post.call_args
    assert "12345" in call_kwargs.args[0]
    assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer tok_test"


@pytest.mark.asyncio
@patch("app.services.intervention.whatsapp_sender.httpx.AsyncClient")
@patch("app.services.intervention.whatsapp_sender.settings")
async def test_send_warning_creates_intervention_log(mock_settings, mock_client_cls, mock_db):
    mock_settings.whatsapp_outbound_enabled = True
    mock_settings.whatsapp_phone_number_id = "12345"
    mock_settings.whatsapp_access_token = "tok_test"

    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=_mock_response())
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    from app.services.intervention.whatsapp_sender import send_whatsapp_warning

    await send_whatsapp_warning("+919876543210", "Scam alert", mock_db)

    mock_db.add.assert_called_once()
    log_entry = mock_db.add.call_args[0][0]
    assert log_entry.intervention_type == "whatsapp_warning"
    assert log_entry.status == "sent"


@pytest.mark.asyncio
@patch("app.services.intervention.whatsapp_sender.httpx.AsyncClient")
@patch("app.services.intervention.whatsapp_sender.settings")
async def test_send_failure_retries_then_fails(mock_settings, mock_client_cls, mock_db):
    mock_settings.whatsapp_outbound_enabled = True
    mock_settings.whatsapp_phone_number_id = "12345"
    mock_settings.whatsapp_access_token = "tok_test"

    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=_mock_response(status_code=400, text="bad request"))
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    from app.services.intervention.whatsapp_sender import send_whatsapp_warning

    result = await send_whatsapp_warning("+919876543210", "Scam alert", mock_db)

    assert result["sent"] is False
    assert result["status"] == "failed"
    assert mock_instance.post.await_count == 2


@pytest.mark.asyncio
@patch("app.services.intervention.whatsapp_sender.settings")
async def test_outbound_disabled_raises(mock_settings, mock_db):
    mock_settings.whatsapp_outbound_enabled = False

    from app.services.intervention.whatsapp_sender import send_whatsapp_warning

    result = await send_whatsapp_warning("+919876543210", "Scam alert", mock_db)

    assert result["sent"] is False
    assert result["status"] == "outbound_disabled"
    mock_db.add.assert_called_once()
