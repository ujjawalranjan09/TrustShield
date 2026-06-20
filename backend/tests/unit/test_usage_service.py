"""Tests for billing usage service — quota checks and usage recording."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.billing.usage_service import check_quota, record_usage, get_usage, _current_bucket


def _make_async_execute(result_value=None, result_side_effect=None):
    """Return a callable suitable for mocking db.execute.

    The service does ``result = await db.execute(stmt)`` followed by
    ``result.scalars().first()``.  We make execute an async function that
    returns a regular (non-coroutine) mock with the scalars chain wired.
    """
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = result_value
    if result_side_effect:
        mock_result.scalars.return_value.first.side_effect = result_side_effect

    async def _execute(*args, **kwargs):
        return mock_result

    return _execute


@pytest.mark.asyncio
async def test_check_quota_free_plan_at_limit():
    """A free plan at the scan limit should return False."""
    mock_db = AsyncMock()

    mock_sub = MagicMock()
    mock_sub.id = 1
    mock_sub.plan_code = "free"

    mock_plan = MagicMock()
    mock_plan.code = "free"
    mock_plan.monthly_scan_limit = 1000
    mock_plan.monthly_webhook_limit = 100

    with patch(
        "app.services.billing.usage_service.resolve_subscription",
        return_value=mock_sub,
    ), patch(
        "app.services.billing.plan_service.get_plan_by_code",
        return_value=mock_plan,
    ), patch(
        "app.services.billing.usage_service.get_usage",
        return_value={"scan_calls": 1000, "webhook_calls": 50},
    ):
        allowed, info = await check_quota(
            mock_db, bank_id="test-bank", endpoint="analyze"
        )

    assert allowed is False
    assert info["remaining"] == 0


@pytest.mark.asyncio
async def test_check_quota_enterprise_unlimited():
    """Enterprise (-1 limit) should always return True."""
    mock_db = AsyncMock()

    mock_sub = MagicMock()
    mock_sub.id = 1
    mock_sub.plan_code = "enterprise"

    mock_plan = MagicMock()
    mock_plan.code = "enterprise"
    mock_plan.monthly_scan_limit = -1
    mock_plan.monthly_webhook_limit = -1

    with patch(
        "app.services.billing.usage_service.resolve_subscription",
        return_value=mock_sub,
    ), patch(
        "app.services.billing.plan_service.get_plan_by_code",
        return_value=mock_plan,
    ):
        allowed, info = await check_quota(
            mock_db, bank_id="test-bank", endpoint="analyze"
        )

    assert allowed is True
    assert info is None


@pytest.mark.asyncio
async def test_record_usage_increments_correctly():
    """Usage recording should increment the correct endpoint counter."""
    mock_db = AsyncMock()
    mock_sub = MagicMock()
    mock_sub.id = 1

    # No existing ledger → first execute returns None
    mock_db.execute = _make_async_execute(result_value=None)

    with patch(
        "app.services.billing.usage_service.resolve_subscription",
        return_value=mock_sub,
    ):
        await record_usage(
            mock_db, bank_id="test-bank", endpoint="analyze", session_id="sess-1"
        )

    # db.add is called twice: ledger first, then event
    assert mock_db.add.call_count == 2
    added = mock_db.add.call_args_list[0][0][0]
    assert added.scan_calls == 1
    assert added.webhook_calls == 0


@pytest.mark.asyncio
async def test_get_usage_returns_correct_shape():
    """get_usage should return the standard fields."""
    mock_db = AsyncMock()

    mock_ledger = MagicMock()
    mock_ledger.scan_calls = 500
    mock_ledger.webhook_calls = 25

    mock_sub = MagicMock()
    mock_sub.plan_code = "pro"

    mock_plan = MagicMock()
    mock_plan.code = "pro"
    mock_plan.monthly_scan_limit = 50000
    mock_plan.monthly_webhook_limit = 10000

    # get_usage calls db.execute twice (ledger then subscription)
    mock_db.execute = _make_async_execute(
        result_side_effect=[mock_ledger, mock_sub]
    )

    # Patch at the source module so the local import inside get_usage resolves
    with patch(
        "app.services.billing.plan_service.get_plan_by_code",
        return_value=mock_plan,
    ):
        usage = await get_usage(mock_db, subscription_id=1)

    assert usage["scan_calls"] == 500
    assert usage["webhook_calls"] == 25
    assert usage["scan_limit"] == 50000
    assert usage["remaining_scan"] == 49500
    assert "percent_used" in usage
    assert "bucket" in usage


@pytest.mark.asyncio
async def test_current_bucket_format():
    """Bucket should be in YYYY-MM format."""
    bucket = _current_bucket()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    expected = f"{now.year:04d}-{now.month:02d}"
    assert bucket == expected
