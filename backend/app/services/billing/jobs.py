"""Nightly billing jobs — usage rollup, Stripe metering, retention."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.models.billing import Subscription, UsageEvent, UsageLedger

logger = logging.getLogger(__name__)


async def nightly_usage_rollup(db_session_factory) -> None:
    """Nightly rollup: reconcile UsageEvent counts with UsageLedger.

    Runs at 00:05 UTC. For each subscription with events in the current
    month bucket, sum events and reconcile against the ledger.  Reports
    a count of corrections made.
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        bucket = f"{now.year:04d}-{now.month:02d}"

        # Get all subscriptions that have recent events
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = (month_start + timedelta(days=32)).replace(day=1)

        sub_ids = await db.execute(
            select(UsageEvent.subscription_id)
            .filter(
                UsageEvent.created_at >= month_start,
                UsageEvent.created_at < month_end,
            )
            .distinct()
        )
        sub_ids = sub_ids.scalars().all()

        corrections = 0
        for sub_id in sub_ids:
            # Count actual events for this subscription/month
            event_counts = await db.execute(
                select(
                    func.sum(
                        func.case((UsageEvent.endpoint == "analyze", 1), else_=0)
                    ).label("scan_count"),
                    func.sum(
                        func.case((UsageEvent.endpoint != "analyze", 1), else_=0)
                    ).label("webhook_count"),
                ).filter(
                    UsageEvent.subscription_id == sub_id,
                    UsageEvent.created_at >= month_start,
                    UsageEvent.created_at < month_end,
                )
            )
            row = event_counts.one()
            actual_scan = row.scan_count or 0
            actual_webhook = row.webhook_count or 0

            # Get existing ledger
            ledger = await db.execute(
                select(UsageLedger).filter(
                    UsageLedger.subscription_id == sub_id,
                    UsageLedger.bucket == bucket,
                )
            )
            ledger_row = ledger.scalars().first()

            if ledger_row:
                if (
                    ledger_row.scan_calls != actual_scan
                    or ledger_row.webhook_calls != actual_webhook
                ):
                    ledger_row.scan_calls = actual_scan
                    ledger_row.webhook_calls = actual_webhook
                    ledger_row.last_call_at = now
                    corrections += 1
            else:
                ledger_row = UsageLedger(
                    subscription_id=sub_id,
                    bucket=bucket,
                    scan_calls=actual_scan,
                    webhook_calls=actual_webhook,
                    last_call_at=now,
                )
                db.add(ledger_row)

        await db.commit()

        # Report metric (just log for now)
        logger.info(
            "Nightly rollup complete: %d subscriptions, %d corrections",
            len(sub_ids),
            corrections,
        )


async def submit_metered_usage_to_stripe() -> None:
    """Push monthly aggregate usage to Stripe as metered records.

    Only runs when billing_enabled=True and stripe is configured.
    """
    from app.config import settings

    if not settings.billing_enabled or not settings.stripe_secret_key:
        logger.info("Stripe metering disabled — skipping")
        return

    try:
        import stripe

        stripe.api_key = settings.stripe_secret_key
    except Exception as exc:
        logger.warning("Stripe metering submission failed (import): %s", exc)
        return

    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        bucket = f"{now.year:04d}-{now.month:02d}"

        subs = await db.execute(
            select(Subscription).filter(
                Subscription.status.in_(["active", "trialing"]),
                Subscription.stripe_subscription_id.isnot(None),
            )
        )
        for sub in subs.scalars().all():
            try:
                ledger = await db.execute(
                    select(UsageLedger).filter(
                        UsageLedger.subscription_id == sub.id,
                        UsageLedger.bucket == bucket,
                    )
                )
                usage = ledger.scalars().first()
                if not usage or usage.scan_calls == 0:
                    continue

                stripe.SubscriptionItem.create_usage_record(
                    sub_item_id=sub.stripe_subscription_id,
                    quantity=usage.scan_calls,
                    timestamp=int(now.timestamp()),
                    action="set",
                )
                logger.info(
                    "Submitted meter usage for sub %s: %d scans",
                    sub.id,
                    usage.scan_calls,
                )
            except Exception as exc:
                logger.warning(
                    "Stripe metering failed for sub %s: %s", sub.id, exc
                )


async def cleanup_old_usage_events() -> int:
    """Delete UsageEvent rows older than 13 months.

    Returns number of deleted rows.
    """
    from app.database import AsyncSessionLocal

    cutoff = datetime.now(timezone.utc) - timedelta(days=395)  # 13 months

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(UsageEvent).filter(UsageEvent.created_at < cutoff)
        )
        await db.commit()
        deleted = result.rowcount
        logger.info("Cleaned up %d old usage events (cutoff=%s)", deleted, cutoff)
        return deleted