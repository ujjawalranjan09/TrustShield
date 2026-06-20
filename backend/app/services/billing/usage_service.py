"""Usage recording, retrieval, and quota enforcement."""

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Subscription, UsageEvent, UsageLedger
from app.services.billing.plan_service import resolve_subscription

logger = logging.getLogger(__name__)


def _current_bucket() -> str:
    """Return 'YYYY-MM' for the current UTC month."""
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


async def record_usage(
    db: AsyncSession,
    *,
    bank_id: Optional[str] = None,
    user_id: Optional[int] = None,
    endpoint: str,
    session_id: Optional[str] = None,
) -> None:
    """Increment the monthly usage ledger and insert a raw event."""
    try:
        sub = await resolve_subscription(db, bank_id=bank_id, user_id=user_id)
        if not sub:
            return

        bucket = _current_bucket()

        # Upsert ledger row
        result = await db.execute(
            select(UsageLedger).filter(
                UsageLedger.subscription_id == sub.id,
                UsageLedger.bucket == bucket,
            )
        )
        ledger = result.scalars().first()
        if ledger:
            if endpoint == "analyze":
                ledger.scan_calls += 1
            else:
                ledger.webhook_calls += 1
            ledger.last_call_at = datetime.now(timezone.utc)
        else:
            ledger = UsageLedger(
                subscription_id=sub.id,
                bucket=bucket,
                scan_calls=1 if endpoint == "analyze" else 0,
                webhook_calls=1 if endpoint != "analyze" else 0,
                last_call_at=datetime.now(timezone.utc),
            )
            db.add(ledger)

        # Insert raw event
        event = UsageEvent(
            subscription_id=sub.id,
            endpoint=endpoint,
            session_id=session_id,
        )
        db.add(event)
        await db.flush()
    except Exception as exc:
        logger.warning("record_usage failed (non-blocking): %s", exc)


async def get_usage(
    db: AsyncSession, subscription_id: int, bucket: Optional[str] = None
) -> dict:
    """Return current usage stats for a subscription."""
    bucket = bucket or _current_bucket()
    result = await db.execute(
        select(UsageLedger).filter(
            UsageLedger.subscription_id == subscription_id,
            UsageLedger.bucket == bucket,
        )
    )
    ledger = result.scalars().first()
    scan_calls = ledger.scan_calls if ledger else 0
    webhook_calls = ledger.webhook_calls if ledger else 0

    # Get plan limits
    sub_result = await db.execute(
        select(Subscription).filter(Subscription.id == subscription_id)
    )
    sub = sub_result.scalars().first()

    from app.services.billing.plan_service import get_plan_by_code
    plan = await get_plan_by_code(db, sub.plan_code) if sub else None
    scan_limit = plan.monthly_scan_limit if plan else 1000
    webhook_limit = plan.monthly_webhook_limit if plan else 100

    return {
        "scan_calls": scan_calls,
        "webhook_calls": webhook_calls,
        "scan_limit": scan_limit,
        "webhook_limit": webhook_limit,
        "remaining_scan": (
            -1 if scan_limit == -1 else max(0, scan_limit - scan_calls)
        ),
        "remaining_webhook": (
            -1 if webhook_limit == -1 else max(0, webhook_limit - webhook_calls)
        ),
        "percent_used": (
            round(scan_calls / scan_limit * 100, 1) if scan_limit > 0 else 0.0
        ),
        "bucket": bucket,
    }


async def check_quota(
    db: AsyncSession,
    *,
    bank_id: Optional[str] = None,
    user_id: Optional[int] = None,
    endpoint: str,
) -> Tuple[bool, Optional[dict]]:
    """Check if the caller has quota remaining. Returns (allowed, quota_info)."""
    sub = await resolve_subscription(db, bank_id=bank_id, user_id=user_id)
    if not sub:
        # No subscription — default to free plan
        from app.services.billing.plan_service import get_plan_by_code
        plan = await get_plan_by_code(db, "free")
    else:
        from app.services.billing.plan_service import get_plan_by_code
        plan = await get_plan_by_code(db, sub.plan_code)

    if not plan:
        plan_code = "free"
        scan_limit = 1000
        webhook_limit = 100
    else:
        plan_code = plan.code
        scan_limit = plan.monthly_scan_limit
        webhook_limit = plan.monthly_webhook_limit

    # Enterprise (unlimited) always allowed
    if scan_limit == -1 and webhook_limit == -1:
        return True, None

    bucket = _current_bucket()
    if sub:
        usage = await get_usage(db, sub.id, bucket)
    else:
        usage = {"scan_calls": 0, "webhook_calls": 0}

    limit = scan_limit if endpoint == "analyze" else webhook_limit
    used = usage["scan_calls"] if endpoint == "analyze" else usage["webhook_calls"]

    if limit > 0 and used >= limit:
        return False, {
            "plan": plan_code,
            "endpoint": endpoint,
            "used": used,
            "limit": limit,
            "remaining": 0,
            "bucket": bucket,
        }

    return True, {
        "plan": plan_code,
        "endpoint": endpoint,
        "used": used,
        "limit": limit,
        "remaining": -1 if limit == -1 else limit - used,
        "bucket": bucket,
    }
