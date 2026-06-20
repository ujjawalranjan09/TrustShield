"""Stripe integration — thin wrapper with graceful degradation."""

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def _stripe_enabled() -> bool:
    return bool(settings.billing_enabled and settings.stripe_secret_key)


def create_checkout_session(
    bank_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> Optional[dict]:
    """Create a Stripe Checkout session. Returns {url, session_id} or None."""
    if not _stripe_enabled():
        logger.warning("Stripe not configured — checkout unavailable")
        return None
    try:
        import stripe
        stripe.api_key = settings.stripe_secret_key
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"bank_id": bank_id},
        )
        return {"url": session.url, "session_id": session.id}
    except Exception as exc:
        logger.error("Stripe checkout failed: %s", exc)
        return None


def create_billing_portal_session(
    stripe_customer_id: str,
    return_url: str,
) -> Optional[dict]:
    """Create a Stripe Customer Portal session. Returns {url} or None."""
    if not _stripe_enabled():
        return None
    try:
        import stripe
        stripe.api_key = settings.stripe_secret_key
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return {"url": session.url}
    except Exception as exc:
        logger.error("Stripe portal failed: %s", exc)
        return None


def construct_webhook_event(payload: bytes, sig_header: str) -> Optional[object]:
    """Verify and construct a Stripe webhook event. Returns event or None."""
    if not _stripe_enabled():
        return None
    try:
        import stripe
        stripe.api_key = settings.stripe_secret_key
        return stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except Exception as exc:
        logger.warning("Stripe webhook verification failed: %s", exc)
        return None


async def handle_subscription_updated(event: object) -> None:
    """Handle customer.subscription.updated event."""
    try:
        sub_data = event["data"]["object"]
        stripe_sub_id = sub_data["id"]
        status = sub_data["status"]

        from app.database import AsyncSessionLocal
        from app.models.billing import Subscription
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Subscription).filter(
                    Subscription.stripe_subscription_id == stripe_sub_id
                )
            )
            sub = result.scalars().first()
            if sub:
                sub.status = status
                if sub_data.get("current_period_end"):
                    from datetime import datetime, timezone
                    sub.current_period_end = datetime.fromtimestamp(
                        sub_data["current_period_end"], tz=timezone.utc
                    )
                await db.commit()
    except Exception as exc:
        logger.error("handle_subscription_updated failed: %s", exc)


async def handle_invoice_paid(event: object) -> None:
    """Handle invoice.paid event — mark period as paid."""
    logger.info("Invoice paid: %s", event.get("id", "unknown"))
