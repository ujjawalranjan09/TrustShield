"""Unit tests for webhook dispatcher and signature verification."""

import json
import time
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.integration.webhook_dispatcher import (
    build_signature_header,
    verify_signature,
    dispatch_event,
    WebhookSubscription,
    REPLAY_TOLERANCE_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_secret():
    return "test_secret_key_32_bytes_long!"


def _make_payload(data=None):
    if data is None:
        data = {"event": "scam_detected", "session_id": "s1", "risk_level": "HIGH"}
    return json.dumps(data, default=str)


def _make_signature_header(secret=None, payload=None, timestamp=None):
    secret = secret or _make_secret()
    payload = payload or _make_payload()
    timestamp = timestamp or int(time.time())
    return build_signature_header(secret, payload, timestamp)


# ---------------------------------------------------------------------------
# Signature tests
# ---------------------------------------------------------------------------

def test_signature_is_valid():
    secret = _make_secret()
    payload = _make_payload()
    timestamp = int(time.time())

    header = build_signature_header(secret, payload, timestamp)
    assert verify_signature(secret, payload, header) is True


def test_tampered_signature_rejected():
    secret = _make_secret()
    payload = _make_payload()
    timestamp = int(time.time())

    header = build_signature_header(secret, payload, timestamp)
    tampered_payload = _make_payload({"event": "tampered"})
    assert verify_signature(secret, tampered_payload, header) is False


def test_old_timestamp_rejected():
    secret = _make_secret()
    payload = _make_payload()
    old_timestamp = int(time.time()) - REPLAY_TOLERANCE_SECONDS - 100

    header = build_signature_header(secret, payload, old_timestamp)
    assert verify_signature(secret, payload, header) is False


def test_wrong_secret_rejected():
    secret = _make_secret()
    wrong_secret = "wrong_secret_key_32_bytes_long_!"
    payload = _make_payload()
    timestamp = int(time.time())

    header = build_signature_header(secret, payload, timestamp)
    assert verify_signature(wrong_secret, payload, header) is False


def test_malformed_header_rejected():
    assert verify_signature(_make_secret(), _make_payload(), "garbage") is False
    assert verify_signature(_make_secret(), _make_payload(), "") is False


# ---------------------------------------------------------------------------
# Dispatch tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_calls_subscriber():
    db = AsyncMock()
    sub = MagicMock(spec=WebhookSubscription)
    sub.id = 1
    sub.tenant_id = "tenant_a"
    sub.url = "https://example.com/hook"
    sub.event_types = json.dumps(["scam_detected"])
    sub.is_active = True
    sub.secret = _make_secret()
    sub.event_type_list = ["scam_detected"]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub]
    db.execute.return_value = mock_result

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("app.services.integration.webhook_dispatcher.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.integration.webhook_dispatcher.asyncio.sleep", new_callable=AsyncMock):
            await dispatch_event("tenant_a", "scam_detected", {"event": "scam_detected"}, db)

    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "https://example.com/hook"
    assert "X-TrustShield-Signature" in call_args[1]["headers"]


@pytest.mark.asyncio
async def test_retry_on_failure():
    db = AsyncMock()
    sub = MagicMock(spec=WebhookSubscription)
    sub.id = 2
    sub.tenant_id = "tenant_a"
    sub.url = "https://example.com/hook"
    sub.event_types = json.dumps(["scam_detected"])
    sub.is_active = True
    sub.secret = _make_secret()
    sub.event_type_list = ["scam_detected"]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub]
    db.execute.return_value = mock_result

    success_response = MagicMock()
    success_response.status_code = 200

    with patch("app.services.integration.webhook_dispatcher.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = [
            Exception("Connection refused"),
            success_response,
        ]
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.integration.webhook_dispatcher.asyncio.sleep", new_callable=AsyncMock):
            await dispatch_event("tenant_a", "scam_detected", {"event": "scam_detected"}, db)

    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_max_retries_disables_subscription():
    db = AsyncMock()
    sub = MagicMock(spec=WebhookSubscription)
    sub.id = 3
    sub.tenant_id = "tenant_a"
    sub.url = "https://example.com/hook"
    sub.event_types = json.dumps(["scam_detected"])
    sub.is_active = True
    sub.secret = _make_secret()
    sub.event_type_list = ["scam_detected"]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub]
    db.execute.return_value = mock_result

    with patch("app.services.integration.webhook_dispatcher.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Persistent failure")
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.integration.webhook_dispatcher.asyncio.sleep", new_callable=AsyncMock):
            await dispatch_event("tenant_a", "scam_detected", {"event": "scam_detected"}, db)

    assert mock_client.post.call_count == 8
    assert sub.is_active is False
    db.commit.assert_called()


@pytest.mark.asyncio
async def test_tenant_isolation():
    """Tenant A events must never reach tenant B subscriptions."""
    db = AsyncMock()

    sub_a = MagicMock(spec=WebhookSubscription)
    sub_a.tenant_id = "tenant_a"
    sub_a.url = "https://a.example.com/hook"
    sub_a.event_types = json.dumps(["scam_detected"])
    sub_a.is_active = True
    sub_a.secret = _make_secret()
    sub_a.event_type_list = ["scam_detected"]

    # When dispatching for tenant_a, only tenant_a's subs should appear
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub_a]
    db.execute.return_value = mock_result

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("app.services.integration.webhook_dispatcher.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.integration.webhook_dispatcher.asyncio.sleep", new_callable=AsyncMock):
            await dispatch_event("tenant_a", "scam_detected", {"event": "scam_detected"}, db)

    assert mock_client.post.call_count == 1
    assert mock_client.post.call_args[0][0] == "https://a.example.com/hook"
