"""Billing API endpoints — usage, subscriptions, checkout, portal."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_async_db
from app.models.billing import Plan
from app.models.user import User
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Schemas ---

class UsageResponse(BaseModel):
    scan_calls: int
    webhook_calls: int
    scan_limit: int
    webhook_limit: int
    remaining_scan: int
    remaining_webhook: int
    percent_used: float
    bucket: str


class SubscriptionResponse(BaseModel):
    plan_code: str
    status: str
    current_period_end: Optional[str] = None
    stripe_customer_id: Optional[str] = None


class CheckoutRequest(BaseModel):
    price_id: str = Field(..., min_length=1)
    success_url: str = Field(..., min_length=1)
    cancel_url: str = Field(..., min_length=1)


class CheckoutResponse(BaseModel):
    url: str
    session_id: str


class PlanResponse(BaseModel):
    code: str
    name: str
    monthly_scan_limit: int
    monthly_webhook_limit: int
    sla_percent: float


# --- Endpoints ---

@router.get("/billing/usage", response_model=UsageResponse)
async def get_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Get current month usage for the authenticated user."""
    from app.services.billing.usage_service import get_usage as svc_get_usage
    from app.services.billing.plan_service import resolve_subscription

    sub = await resolve_subscription(db, user_id=current_user.id)
    if not sub:
        # Default to free plan usage
        return UsageResponse(
            scan_calls=0, webhook_calls=0,
            scan_limit=1000, webhook_limit=100,
            remaining_scan=1000, remaining_webhook=100,
            percent_used=0.0, bucket="",
        )

    usage = await svc_get_usage(db, sub.id)
    return UsageResponse(**usage)


@router.get("/billing/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Get current subscription details."""
    from app.services.billing.plan_service import resolve_subscription

    sub = await resolve_subscription(db, user_id=current_user.id)
    if not sub:
        return SubscriptionResponse(plan_code="free", status="active")

    return SubscriptionResponse(
        plan_code=sub.plan_code,
        status=sub.status,
        current_period_end=(
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        stripe_customer_id=sub.stripe_customer_id,
    )


@router.post("/billing/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    current_user: User = Depends(get_current_user),
):
    """Create a Stripe Checkout session for plan upgrade."""
    from app.services.billing.stripe_service import create_checkout_session

    result = create_checkout_session(
        bank_id="",
        price_id=request.price_id,
        success_url=request.success_url,
        cancel_url=request.cancel_url,
    )
    if not result:
        raise HTTPException(
            status_code=503,
            detail="Billing is not configured. Contact support.",
        )
    return CheckoutResponse(url=result["url"], session_id=result["session_id"])


@router.post("/billing/portal")
async def create_portal(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Create a Stripe Customer Portal session."""
    from app.services.billing.stripe_service import create_billing_portal_session
    from app.services.billing.plan_service import resolve_subscription

    sub = await resolve_subscription(db, user_id=current_user.id)
    if not sub or not sub.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No active Stripe subscription")

    result = create_billing_portal_session(
        stripe_customer_id=sub.stripe_customer_id,
        return_url="/dashboard/billing",
    )
    if not result:
        raise HTTPException(status_code=503, detail="Billing portal unavailable")
    return {"url": result["url"]}


@router.get("/billing/plans", response_model=list[PlanResponse])
async def list_plans(
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(get_current_user),
):
    """List available billing plans."""
    result = await db.execute(select(Plan).filter(Plan.is_active))
    plans = result.scalars().all()
    return [
        PlanResponse(
            code=p.code,
            name=p.name,
            monthly_scan_limit=p.monthly_scan_limit,
            monthly_webhook_limit=p.monthly_webhook_limit,
            sla_percent=p.sla_percent,
        )
        for p in plans
    ]


# --- Stripe Webhook (no auth required) ---

@router.post("/billing/stripe-webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events. No auth — Stripe calls this directly."""
    from app.services.billing.stripe_service import (
        construct_webhook_event,
        handle_subscription_updated,
        handle_invoice_paid,
    )

    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")

    event = construct_webhook_event(payload, sig_header)
    if event is None:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event.get("type", "")

    if event_type == "customer.subscription.updated":
        await handle_subscription_updated(event)
    elif event_type == "customer.subscription.deleted":
        await handle_subscription_updated(event)
    elif event_type == "invoice.paid":
        await handle_invoice_paid(event)
    elif event_type == "checkout.session.completed":
        # Create/update subscription from checkout
        pass

    return {"received": True}
